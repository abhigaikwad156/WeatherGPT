import type { CurrentLocation, FarmLocation } from "../api/types";

type NamedLocation = Pick<CurrentLocation, "location_name"> | Pick<FarmLocation, "location_name">;

/** A future reverse-geocoding provider can populate location_name without changing UI callers. */
export function locationDisplayName(location: NamedLocation | null): string {
  return location?.location_name?.trim() || "Location saved";
}
