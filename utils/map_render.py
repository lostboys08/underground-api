"""
Utilities for server-side map rendering using Playwright.

Renders GeoJSON features onto a Leaflet map and returns a PNG screenshot.
This is intended to generate small map images for inclusion in emails.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from playwright.async_api import async_playwright


logger = logging.getLogger(__name__)


def _to_feature_collection(features: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Convert a list of GeoJSON Features into a FeatureCollection.
    If a single FeatureCollection is already provided as the only item,
    it will be returned as-is.
    """
    if len(features) == 1 and features[0].get("type") == "FeatureCollection":
        return features[0]
    return {"type": "FeatureCollection", "features": features}


async def render_map_png_from_features(
    features: List[Dict[str, Any]],
    *,
    width: int = 600,
    height: int = 400,
    padding: int = 20,
    tile_url_template: str = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    tile_attribution: str = "&copy; OpenStreetMap contributors",
) -> bytes:
    """
    Render a PNG map image from a list of GeoJSON features.

    Args:
        features: List of GeoJSON Feature dicts (or a single FeatureCollection wrapped in a list).
        width: Image width in pixels.
        height: Image height in pixels.
        padding: Pixel padding for fitBounds.
        tile_url_template: Leaflet tile layer URL template.
        tile_attribution: Attribution HTML string for the tile layer.

    Returns:
        PNG bytes.
    """
    if not features:
        raise ValueError("features must not be empty")

    feature_collection = _to_feature_collection(features)

    # Minimal HTML shell with Leaflet assets and a map container
    html = f"""
<!doctype html>
<html>
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <link
      rel=\"stylesheet\"
      href=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.css\"
      integrity=\"sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=\"
      crossorigin=\"anonymous\"
    />
    <style>
      html, body {{ margin: 0; padding: 0; }}
      #map {{ width: {width}px; height: {height}px; }}
      .leaflet-container {{ background: #e2e8f0; }}
    </style>
  </head>
  <body>
    <div id=\"map\"></div>
    <script
      src=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js\"
      integrity=\"sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=\"
      crossorigin=\"anonymous\"
    ></script>
  </body>
</html>
"""

    # Serialize data and options for injection
    fc_json = json.dumps(feature_collection)
    options = {
        "tileUrl": tile_url_template,
        "tileAttribution": tile_attribution,
        "padding": padding,
    }

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                viewport={"width": width, "height": height},
                device_scale_factor=2,  # crisp on HiDPI
            )
            page = await context.new_page()
            await page.set_content(html, wait_until="domcontentloaded")

            # Initialize the map and data layer in the page context
            init_script = """
                (fc, opts) => {
                  return new Promise((resolve) => {
                    const map = L.map('map', {
                      zoomControl: false,
                      attributionControl: false,
                    });

                    const tile = L.tileLayer(opts.tileUrl, {
                      attribution: opts.tileAttribution,
                      maxZoom: 20,
                    }).addTo(map);

                    const layer = L.geoJSON(fc, {
                      style: () => ({ color: '#2563eb', weight: 3, opacity: 0.9 }),
                      pointToLayer: (feature, latlng) => L.circleMarker(latlng, {
                        radius: 5,
                        color: '#1e293b',
                        fillColor: '#0ea5e9',
                        fillOpacity: 0.9,
                        weight: 1,
                      }),
                    }).addTo(map);

                    // Fit to data bounds or default view
                    let bounds;
                    try { bounds = layer.getBounds(); } catch (_) { bounds = null; }
                    if (bounds && bounds.isValid && bounds.isValid()) {
                      map.fitBounds(bounds, { padding: [opts.padding, opts.padding] });
                    } else {
                      map.setView([39.5, -98.35], 3); // US default
                    }

                    // Resolve when tiles and layer are ready
                    let tilesLoaded = false;
                    let settled = false;
                    const settle = () => {
                      if (settled) return;
                      settled = true;
                      // Small delay to let labels paint
                      setTimeout(resolve, 200);
                    };

                    tile.on('load', () => { tilesLoaded = true; settle(); });
                    map.on('idle', () => { if (tilesLoaded) settle(); });

                    // Safety timeout
                    setTimeout(settle, 1500);
                  });
                }
            """
            await page.evaluate(init_script, json.loads(fc_json), options)

            # Screenshot only the map element for a tight image
            map_el = await page.query_selector('#map')
            if not map_el:
                raise RuntimeError("Map container not found after initialization")

            png_bytes = await map_el.screenshot(type="png")
            return png_bytes

        except Exception as e:
            logger.error(f"Map rendering failed: {str(e)}")
            raise
        finally:
            try:
                await browser.close()
            except Exception:
                pass


