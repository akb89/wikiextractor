class Frame(object):

    def __init__(self, title='', args=[], prev=None):
        self.title = title
        self.args = args
        self.prev = prev
        self.depth = prev.depth + 1 if prev else 0


    def push(self, title, args):
        return Frame(title, args, self)


    def pop(self):
        return self.prev


    def __str__(self):
        res = ''
        prev = self.prev
        while prev:
            if res: res += ', '
            res += '(%s, %s)' % (prev.title, prev.args)
            prev = prev.prev
        return '<Frame [' + res + ']>'
