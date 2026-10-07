"""Isolated prototype only; stdlib XML tree with explicit namespace/ownership policy.

Not a general lxml compatibility library. Exclusive canonical output supports
the signed template's element/property subset; unsupported cases fail closed.
"""
import copy
import io
import re
import xml.etree.ElementTree as ET

XML = 'http://www.w3.org/XML/1998/namespace'
POLICY = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
          'xml':XML, 'pkg':'http://schemas.microsoft.com/office/2006/xmlPackage',
          'rel':'http://schemas.openxmlformats.org/package/2006/relationships',
          'mc':'http://schemas.openxmlformats.org/markup-compatibility/2006',
          'w14':'http://schemas.microsoft.com/office/word/2010/wordml'}

class Element(ET.Element):
    def __init__(self, tag, attrib=None, nsmap=None, **extra):
        super().__init__(tag, attrib or {}, **extra)
        self.nsmap = dict(nsmap or {})
        self._parent = None
    def _adopt(self, child):
        if not isinstance(child, Element): raise TypeError('adapter-owned nodes required')
        if child is self or any(x is child for x in self._ancestors()): raise ValueError('cycle')
        if child._parent is not None: child._parent.remove(child)
        child._parent = self
    def _ancestors(self):
        n=self._parent
        while n is not None:
            yield n; n=n._parent
    def append(self, child):
        self._adopt(child); super().append(child)
    def insert(self, index, child):
        self._adopt(child); super().insert(index,child)
    def extend(self, children):
        for child in children: self.append(child)
    def remove(self, child):
        super().remove(child); child._parent=None
    def replace(self, old, new):
        index=list(self).index(old); self.remove(old); self.insert(index,new)
    def addprevious(self, new):
        parent=self._parent
        if parent is None: raise ValueError('no parent')
        parent.insert(list(parent).index(self),new)
    def __deepcopy__(self, memo):
        result=Element(self.tag,dict(self.attrib),dict(self.nsmap));memo[id(self)]=result
        result.text=self.text;result.tail=self.tail
        for child in self: result.append(copy.deepcopy(child,memo))
        return result

def SubElement(parent,tag,attrib=None,**extra):
    node=Element(tag,attrib,nsmap=parent.nsmap,**extra);parent.append(node);return node

class XMLParser:
    def __init__(self, *, resolve_entities=False, no_network=True):
        if resolve_entities or not no_network: raise ValueError('unsafe parser option')

def fromstring(payload, parser=None):
    # Decode before declaration checks, including UTF16/32; do not regex raw bytes.
    if isinstance(payload, bytes):
        if payload.startswith((b'\xff\xfe\x00\x00',b'\x00\x00\xfe\xff')): text=payload.decode('utf-32')
        elif payload.startswith((b'\xff\xfe',b'\xfe\xff')): text=payload.decode('utf-16')
        elif payload.startswith(b'\x00<\x00?'): text=payload.decode('utf-16-be')
        elif payload.startswith(b'<\x00?\x00'): text=payload.decode('utf-16-le')
        else: text=payload.decode('utf-8-sig')
    else: text=payload
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)\b',text,re.I):
        raise ValueError('DTD/entity declarations rejected by prototype policy')
    builder=ET.TreeBuilder(element_factory=Element,insert_comments=True,insert_pis=True,
        comment_factory=lambda value: _special(ET.Comment,value),
        pi_factory=lambda target,value: _special(ET.ProcessingInstruction,target+(' '+value if value else '')))
    it=ET.iterparse(io.StringIO(text),events=('start','end','start-ns'),parser=ET.XMLParser(target=builder))
    stack=[];pending={}
    for event,node in it:
        if event=='start-ns': pending[node[0] or None]=node[1]
        elif event=='start':
            node.nsmap=dict(stack[-1].nsmap) if stack else {};node.nsmap.update(pending);pending={}
            if stack: node._parent=stack[-1]
            stack.append(node)
        else: stack.pop()
    return it.root

def _special(kind,value):
    n=Element(kind);n.text=value;return n

def _escape(s,attr=False):
    s=(s or '').replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('\r','&#13;')
    return s.replace('"','&quot;').replace('\t','&#9;').replace('\n','&#10;') if attr else s

def _split(name):
    if name.startswith('{'): return name[1:].split('}',1)
    return '',name

def tostring(node,encoding='ASCII',method='xml',exclusive=False,**options):
    canonical=method=='c14n'
    if method not in ('xml','c14n') or (canonical and not exclusive): raise ValueError('unsupported serialization')
    if options: raise ValueError('unsupported serialization options')
    def emit(n,context,available):
        if n.tag is ET.Comment:
            return '<!--'+(n.text or '')+'-->'+_escape(n.tail)
        if n.tag is ET.ProcessingInstruction:
            return '<?'+(n.text or '')+'?>'+_escape(n.tail)
        available=dict(available);available.update(n.nsmap);available['xml']=XML
        declarations={} if canonical else {k:v for k,v in n.nsmap.items() if k!='xml' and context.get(k)!=v}
        def qualify(name,attribute=False):
            uri,local=_split(name)
            if not uri: return local
            candidates=[k for k,v in available.items() if v==uri and (k is not None or not attribute)]
            if candidates: prefix=candidates[0]
            else:
                prefix=next((k for k,v in POLICY.items() if v==uri),'')
                if not prefix:
                    i=0
                    while 'ns'+str(i) in available: i+=1
                    prefix='ns'+str(i)
                if prefix in available and available[prefix]!=uri: raise ValueError('prefix conflict')
                available[prefix]=uri
            if prefix!='xml' and context.get(prefix)!=uri: declarations[prefix]=uri
            return (prefix+':' if prefix else '')+local
        tag=qualify(n.tag)
        attrs=[(qualify(k,True),v,k) for k,v in n.attrib.items()]
        # Values with lexical QNames, plus MC's lists of namespace prefixes.
        for key,value in n.attrib.items():
            uri,local=_split(key)
            refs=set(re.findall(r'(?<![\w/])([A-Za-z_][\w.-]*):[A-Za-z_][\w.-]*',value)) if '://' not in value else set()
            if uri==POLICY['mc'] and local in ('Ignorable','MustUnderstand'): refs.update(value.split())
            if uri==POLICY['mc'] and local in ('PreserveElements','PreserveAttributes','ProcessContent'):
                refs.update(token.split(':',1)[0] for token in value.split() if ':' in token)
            for prefix in refs:
                if prefix not in available: raise ValueError('unresolved QName prefix: '+prefix)
                if not canonical and context.get(prefix)!=available[prefix]: declarations[prefix]=available[prefix]
        # Unnamespaced elements under a default namespace require explicit reset.
        if not _split(n.tag)[0] and context.get(None): declarations[None]=''
        rendered=context.copy();rendered.update(declarations)
        decls=sorted(declarations.items(),key=lambda pair:pair[0] or '') if canonical else declarations.items()
        start='<'+tag+''.join(' xmlns'+(':'+p if p else '')+'="'+_escape(u,True)+'"' for p,u in decls)
        if canonical: attrs.sort(key=lambda a:tuple(_split(a[2])))
        start+=''.join(' '+k+'="'+_escape(v,True)+'"' for k,v,_ in attrs)
        if not len(n) and not n.text and not canonical: result=start+'/>'
        else: result=start+'>'+_escape(n.text)+''.join(emit(c,rendered,available) for c in n)+'</'+tag+'>'
        return result+_escape(n.tail)
    text=emit(node,{'xml':XML},{'xml':XML})
    if encoding=='unicode': return text
    # lxml's default ASCII escapes non-ASCII with numeric references.
    return text.encode('utf-8' if canonical else encoding,errors='xmlcharrefreplace')
