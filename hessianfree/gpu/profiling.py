import ast
import pstats
import sys
import time
from cProfile import Profile

import numpy as np
import pycuda
import pycuda.autoinit
from pycuda import gpuarray

import hessianfree as hf


def threshold_calc_G():
    """Profile GPU vs CPU performance (can use this to determine at what point
    it is useful to run things on the GPU)."""

    batch_size = range(128, 1024, 128)
    layer_size = range(128, 1024, 128)
    reps = 100

    times = np.zeros((len(batch_size), len(layer_size), 2))
    for i, b in enumerate(batch_size):
        inputs = np.random.randn(b, 1).astype(np.float32)
        targets = np.random.randn(b, 1).astype(np.float32)

        for j, n in enumerate(layer_size):
            ff = hf.FFNet([1, n, n, 1], use_GPU=False)
            ff.cache_minibatch(inputs, targets)

            v = np.random.randn(ff.W.size).astype(np.float32)

            start = time.time()
            for _ in range(reps):
                ff.calc_G(v)
            times[i, j, 0] = time.time() - start

            ff = hf.FFNet([1, n, n, 1], use_GPU=True)
            ff.cache_minibatch(inputs, targets)

            start = time.time()
            for _ in range(reps):
                ff.GPU_calc_G(v)
            times[i, j, 1] = time.time() - start

            print "b", b, "n", n, "times", times[i, j]

    print times[..., 1] - times[..., 0]
    print times[..., 1] < times[..., 0]


def threshold_m_dot():
    """Profile CPU vs GPU performance."""

    vec_size = range(128, 1024, 128)
    reps = 100
    times = np.zeros((len(vec_size), len(vec_size), len(vec_size), 2))
    for i, a0 in enumerate(vec_size):
        for j, a1 in enumerate(vec_size):
            a = np.random.randn(a0, a1).astype(np.float32)
            for k, b1 in enumerate(vec_size):
                b = np.random.randn(a1, b1).astype(np.float32)
                out = np.zeros((a0, b1), dtype=np.float32)

                start = time.time()
                for _ in range(reps):
                    np.dot(a, b, out=out)
                times[i, j, k, 0] = time.time() - start

                start = time.time()
                a_gpu = gpuarray.to_gpu(a)
                b_gpu = gpuarray.to_gpu(b)
                out_gpu = gpuarray.to_gpu(out)

                for _ in range(reps):
                    hf.gpu.m_dot(a_gpu, b_gpu, out=out_gpu)
                out_gpu.get(out)
                times[i, j, k, 1] = time.time() - start

                print "a0", a0, "a1", a1, "b1", b1, "times", times[i, j, k]

    print times[..., 1] - times[..., 0]
    print times[..., 1] < times[..., 0]


def profile_calc_G(cprofile=True):
    inputs = np.random.randn(1024, 1).astype(np.float32)
    targets = np.random.randn(1024, 1).astype(np.float32)
    N = 1024

    ff = hf.FFNet([1, N, N, 1], use_GPU=True)
    ff.cache_minibatch(inputs, targets)

    v = np.random.randn(ff.W.size).astype(np.float32)

    for _ in range(5):
        # run it a few times to get rid of any startup overhead
        ff.GPU_calc_G(v)

    if cprofile:
        start = time.time()

        p = Profile()
        p.enable()
    else:
        pycuda.driver.start_profiler()

    for _ in range(100):
        _ = ff.GPU_calc_G(v)

    if cprofile:
        p.disable()

        print "time", time.time() - start

        ps = pstats.Stats(p)
        ps.strip_dirs().sort_stats('time').print_stats(20)
    else:
        pycuda.driver.stop_profiler()


def profile_m_dot(cprofile=True):
#     pycuda.compiler.DEFAULT_NVCC_FLAGS += ["-use_fast_math"]

    N = 1024
    a = np.random.randn(N, N).astype(np.float32)
    b = np.random.randn(N, N).astype(np.float32)
    c = np.zeros((N, N), dtype=np.float32)
    a_gpu = gpuarray.to_gpu(a)
    b_gpu = gpuarray.to_gpu(b)
    c_gpu = gpuarray.zeros((N, N), np.float32)

    for _ in range(2):
        # run it a few times to get rid of any startup overhead
        hf.gpu.m_dot(a_gpu, b_gpu, out=c_gpu)
        hf.gpu.simple_m_dot(a_gpu, b_gpu, out=c_gpu)

    if cprofile:
        start = time.time()

        p = Profile()
        p.enable()
    else:
        pycuda.autoinit.context.synchronize()
        pycuda.driver.start_profiler()

    for _ in range(100):
#        np.dot(a, b, out=c)
#        simple_m_dot(a_gpu, b_gpu, out=c_gpu)
        hf.gpu.m_dot(a_gpu, b_gpu, out=c_gpu, transpose_a=True,
                     transpose_b=True)
    c_gpu.get()

    if cprofile:
        p.disable()

        print "time", time.time() - start

        ps = pstats.Stats(p)
        ps.strip_dirs().sort_stats('time').print_stats(20)
    else:
        pycuda.driver.stop_profiler()

if __name__ == "__main__":
    if sys.argv[1] in locals():
        locals()[sys.argv[1]](*[ast.literal_eval(a) for a in sys.argv[2:]])
    else:
        print "Unknown profile function (%s)" % sys.argv[1]