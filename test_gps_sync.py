import os
import sys

# Add the current directory to sys.path to find 'app'
sys.path.append(os.getcwd())

from rapidfuzz import fuzz
from app.Services.geocoding_service import GeocodingService

def test_geocoder():
    # Path to the geojson (from the geocoder's default search)
    # C:\Users\amcgrean\python\gps\source.geojson.gz
    
    print("Initializing GeocodingService...")
    geocoder = GeocodingService()
    
    if not geocoder.is_loaded:
        print("FAILED: Geocoder failed to load index.")
        return

    print(f"Index size: {len(geocoder.exact_idx)}")
    with open("geocoding_debug.txt", "w") as f:
        f.write(f"Index size: {len(geocoder.exact_idx)}\n")
        f.write("Sample keys:\n")
        for k in list(geocoder.exact_idx.keys())[:50]:
            f.write(f"  {k}\n")

    # Test address: 1234 Dodge St, Omaha, NE (Mocked in previous steps, but let's try a real one from the Iowa index)
    # From match_all_jobs_to_geojson.py, common addresses are in Des Moines/West Des Moines
    
    test_addresses = [
        ("621 NE 5TH ST", "GRIMES", "50111"), # Known address from debug log
        ("621 N.E. 5th Street", "Grimes", "50111"), # Fuzzy check
        ("900 FIRST ST", "GRIMES", "50111"),
    ]
    
    # Enable internal fuzzy logging for debug
    import logging
    
    for addr, city, zip_code in test_addresses:
        print(f"\nTesting: {addr}, {city}, {zip_code}")
        
        # Internal debug check
        zip5 = geocoder._norm_zip(zip_code)
        norm_c = geocoder._norm_city(city)
        job_key = geocoder._make_key(addr, city, "IA", zip5)
        print(f"Norm Key: {job_key}")
        
        lat, lon, status = geocoder.geocode_address(addr, city, zip_code)
        if lat:
            print(f"SUCCESS: Found {lat}, {lon} (status: {status})")
        else:
            print(f"FAILED: Status {status}")
            # If failed, let's see why fuzzy might have failed if Zip Pool is > 0
            if status == "failed" and zip5 in geocoder.by_zip_idx:
                print(f"Checking ZIP pool ({len(geocoder.by_zip_idx[zip5])} keys)...")
                job_hn = geocoder._leading_housenumber(addr)
                job_core = geocoder._street_core(addr)
                print(f"Job HN: {job_hn}, Job Core: {job_core}")
                found_hn = 0
                for ck in geocoder.by_zip_idx[zip5]:
                    rec = geocoder.exact_idx[ck][0]
                    if rec[5] == job_hn:
                        found_hn += 1
                        c_sim = fuzz.token_set_ratio(job_core, rec[6])
                        if c_sim > 70:
                            print(f"  Cand: {ck} | Core: {rec[6]} | Sim: {c_sim}")
                print(f"Candidates with same HN: {found_hn}")

if __name__ == "__main__":
    test_geocoder()
