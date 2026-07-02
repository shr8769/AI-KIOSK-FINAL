import sys
sys.path.insert(0, 'backend')
import logging
logging.basicConfig(level=logging.INFO)
from riar.retrievers.entity_resolver import EntityResolver

resolver = EntityResolver()
print("Query: 'where is the physics lab'")
print("Normalized:", resolver.normalize("where is the physics lab"))
res = resolver.resolve("where is the physics lab")
print("Result:", res)
