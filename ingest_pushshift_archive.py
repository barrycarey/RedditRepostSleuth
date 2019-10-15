import zstd

with open("/home/barry/Downloads/RS_2018-12.zst", 'rb') as fh:
    r = zstd.decompress(fh.read())
    print('')