import ee

ee.Initialize(project="vineyard-vigor")

aoi = ee.Geometry.Point([-119.5000, 49.2000]).buffer(500)  # example AOI; set to your own site
window = ("2024-07-01", "2024-08-01")

s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
      .filterBounds(aoi).filterDate(*window))
csp = (ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED")
       .filterBounds(aoi).filterDate(*window))

print("S2 scenes:", s2.size().getInfo())
print("Cloud Score+ scenes:", csp.size().getInfo())