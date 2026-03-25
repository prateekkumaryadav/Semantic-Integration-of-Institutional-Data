from rdflib import Graph

g = Graph()
g.parse("iiitb_master.owl")
for s, p, o in g:
    print(s, p, o)
