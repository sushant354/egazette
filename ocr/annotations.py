import cgi

class Node:
    def __init__(self, start, end, tag, parent, attrs):
        self.start  = start
        self.end    = end
        self.tag    = tag
        self.parent = parent
        self.children = []

        if attrs:
            self.attrs = attrs
        else:
            self.attrs = []

    def __str__(self):
        s = '(%d, %d) tag: %s' % (self.start, self.end, self.tag)
        if self.attrs:
            s += ' attrs: %s' % self.attrs
        if self.children:
            s += ' children: %d' % len(self.children)
        return '{%s}' % s

    def __repr__(self):
        return self.__str__()

    def add_child(self, child):
        #assert child.start >= self.start and child.end <= self.end
        self.children.append(child)

def get_id(tag, idmap):
    if tag in idmap:
        idmap[tag] += 1
    else:
        idmap[tag] = 1
    return idmap[tag]

def annotate_doc(doc, nodelist):
    inserts    = []
    idmap      = {}
    segmentmap = {}
    flatten_nodes(nodelist, inserts, idmap, segmentmap)
    #print len(segmentmap.keys())
    return insert_markers(doc, inserts), segmentmap

def insert_markers(text, inserts):
    sections = []
    lastpos  = 0
    for pos, marker in inserts:
        if pos > lastpos:
            sections.append(cgi.escape(text[lastpos:pos]))
        elif pos < lastpos:
             print ("INVALID MARKER", pos, marker, inserts)
             assert 0
        sections.append(marker)
        lastpos = pos

    if lastpos < len(text):
        sections.append(cgi.escape(text[lastpos:]))

    return u''.join(sections)

def flatten_nodes(nodelist, inserts, idmap, segmentmap):
    for node in nodelist:
        attrlist = node.attrs[:]

        id1 = '%s_%d' % (node.tag, get_id(node.tag, idmap))
        attrlist.append(('id', id1))

        attrs = ' '.join('%s="%s"' % (attr[0], attr[1]) for attr in attrlist)
        if attrs:
            start_tag = '<%s %s>' % (node.tag, attrs)
        else:
            start_tag = '<%s>' % node.tag
        inserts.append((node.start, start_tag))

        if node.tag not in segmentmap:
            segmentmap[node.tag] = []
        segmentmap[node.tag].append(node.start)

        flatten_nodes(node.children, inserts, idmap, segmentmap)
        inserts.append((node.end, '</%s>' % node.tag))

