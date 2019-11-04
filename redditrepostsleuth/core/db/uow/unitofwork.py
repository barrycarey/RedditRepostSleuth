
class UnitOfWork():

    def __enter__(self):
        raise NotImplemented

    def __exit__(self, exc_type, exc_val, exc_tb):
        raise NotImplemented

