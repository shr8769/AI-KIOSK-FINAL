import sys
sys.path.append(r"C:\AI-KIOSK\backend")

from app.services.navigation_service import LocationResolver

resolver = LocationResolver()
res = resolver.resolve("where is the cafeteria")
print("RESULT:", res)
