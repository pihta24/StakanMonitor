import time


class SelfCleaningDict(dict):

    def __init__(self, time_out=3600, prone_interval=None):
        self.timeout = time_out
        self.prone_interval = time_out // 10 or prone_interval
        self.last_prone = None
        if not self.timeout:
            raise ValueError("Timeout cannot be None")

        super().__init__()

    def prone(self):
        """>
        Remove all items that timed out.
        Keys are ordered by last change.
        So we iterate over the first n keys, removing timed out values, until we hit the first still active item.
        Considerations:
        For many items it might make sense to not use list(self.items)
        and rather use a generator to only iterate over the first x items.
        But this would require some (but not much) more effort if done efficiently.
        """
        cur = time.time()
        for key, value in list(self.items()):
            if (value[1] + self.timeout) < cur:
                del self[key]
            else:
                break
        self.last_prone = cur

    def __setitem__(self, key, value):
        cur = time.time()
        v = (value, cur)
        super().__setitem__(key, v)

        if self.prone_interval and self.last_prone and cur < self.last_prone + self.prone_interval:
            self.prone()

    def __getitem__(self, key):
        v = super().__getitem__(key)
        if v:
            v = v[0]
        return v

    def __delitem__(self, key):
        super().__delitem__(key)

