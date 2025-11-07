from math import radians, degrees, sin, cos, atan2, sqrt, isnan
import numpy as np

def _interp_polar(polar, tws, twa):
    # bilinear interpolation on (tws, twa)
    tws_grid = np.array(polar['tws_kn'])
    twa_grid = np.array(polar['twa_deg'])
    V = np.array(polar['target_kn'])  # shape [len(tws), len(twa)]
    tws = float(tws); twa = float(twa)
    # clamp
    tws = np.clip(tws, tws_grid.min(), tws_grid.max())
    twa = np.clip(twa, twa_grid.min(), twa_grid.max())
    # indices
    i = np.searchsorted(tws_grid, tws, side='right') - 1
    j = np.searchsorted(twa_grid, twa, side='right') - 1
    i = np.clip(i, 0, len(tws_grid)-2)
    j = np.clip(j, 0, len(twa_grid)-2)
    # corners
    t0, t1 = tws_grid[i], tws_grid[i+1]
    a0, a1 = twa_grid[j], twa_grid[j+1]
    Q11, Q12 = V[i, j], V[i, j+1]
    Q21, Q22 = V[i+1, j], V[i+1, j+1]
    # weights
    if (t1 - t0) == 0 or (a1 - a0) == 0:
        return float(Q11)
    ft = (tws - t0) / (t1 - t0)
    fa = (twa - a0) / (a1 - a0)
    v = (Q11*(1-ft)*(1-fa) + Q21*ft*(1-fa) + Q12*(1-ft)*fa + Q22*ft*fa)
    return float(v)

def bearing_and_distance(lat1, lon1, lat2, lon2):
    # Haversine distance (meters) + initial bearing (deg)
    R = 6371000.0
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    a = sin(dphi/2)**2 + cos(p1)*cos(p2)*sin(dl/2)**2
    d = 2*R*sqrt(a)
    y = sin(dl) * cos(p2)
    x = cos(p1)*sin(p2) - sin(p1)*cos(p2)*cos(dl)
    brg = (degrees(atan2(y, x)) + 360) % 360
    return brg, d

def start_line_bias(pin_brg, com_brg, twd):
    # line direction is bearing from pin->com
    line_dir = (com_brg - pin_brg) % 360
    # bias is angle between wind and line perpendicular
    perp = (line_dir + 90) % 360
    diff = ((twd - perp + 540) % 360) - 180
    return diff  # + => pin end favored

def time_to_line(distance_m, sog_kn):
    # 1 kn = 0.514444 m/s
    if sog_kn <= 0:
        return float('inf')
    return distance_m / (sog_kn * 0.514444)

def target_twa_upwind(polar, tws):
    # choose min angle where boat speed / cos(angle) maximizes (VMG upwind)
    angles = np.array(polar['twa_deg'])
    speeds = np.array([_interp_polar(polar, tws, a) for a in angles])
    vmg = speeds * np.cos(np.deg2rad(angles))
    idx = np.argmax(vmg[:len(angles)//2])  # upwind half
    return float(angles[idx]), float(speeds[idx])

def layline_recommendation(lat, lon, mark_lat, mark_lon, twd, polar, tws, current_twa):
    brg, dist = bearing_and_distance(lat, lon, mark_lat, mark_lon)
    # target upwind twa
    targ_twa, targ_speed = target_twa_upwind(polar, tws)
    # tacking angle ~ 2 * target TWA
    tack_angle = 2 * targ_twa
    rel = ((brg - twd + 360) % 360)
    # If we're outside layline cone, suggest tack toward closest layline
    left = (twd + 180 - tack_angle/2) % 360
    right = (twd + 180 + tack_angle/2) % 360
    # Decide which board is closer
    # Simple heuristic: compare current_twa to target
    delta = abs(current_twa - targ_twa)
    action = "HOLD" if delta < 5 else ("TACK PORT" if rel > 180 else "TACK STARBOARD")
    return {
        "bearing_to_mark": brg,
        "distance_m": dist,
        "target_twa_deg": targ_twa,
        "target_boat_speed_kn": targ_speed,
        "recommendation": action
    }
