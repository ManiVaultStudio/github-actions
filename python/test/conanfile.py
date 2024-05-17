def compatibility(os, compiler, compiler_version):
    print(f"{os} {compiler} {compiler_version}")
    return """hdf5/1.12.1:compiler.version=13
lz4/1.9.2:compiler.version=13
zlib/1.2.13:compiler.version=13
"""