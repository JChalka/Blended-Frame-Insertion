#!/usr/bin/env python3
"""
Generate modular patch plan batches with WHITE CHANNEL support.

Key change: Tans/browns/skin tones now use w16 to add brightness without
desaturating toward gray. Example: brown = (R=1.0, G=0.5, B=0.25, W=0.3)
keeps the warm RGB ratio while adding brightness via white channel.

Each batch optimized for 4096-bucket transfer curve system.
"""

import csv
from pathlib import Path


def generate_warm_saturation_batch():
    """Extended warm colors with both chromatic and RGB+W variants.

    Includes:
    - RGB-only warm hues (yellow/orange/amber family)
    - Warm-white and neon-like warm variants using white channel
      for bright yellows, oranges, pinks, and highlight-rich warm scenes.
    """
    patches = []

    # RGB-only warm baseline.
    for base_q16 in [8000, 12000, 16000, 20000, 24000, 28000, 32000, 36000, 40000, 45000, 50000, 55000, 60000]:
        # For each base brightness, add warm hues at varying saturation
        # Red dominant: full red, partial green (yellow/orange)
        for g_ratio in [0.2, 0.3, 0.4, 0.5, 0.6, 0.7]:  # red + some green = yellow/orange
            for b_ratio in [0.0, 0.1, 0.2]:  # red + green + small blue variations
                r16 = min(65535, int(base_q16 * 1.0))
                g16 = min(65535, int(base_q16 * g_ratio))
                b16 = min(65535, int(base_q16 * b_ratio))
                
                # Only include if we have meaningful warm component
                if r16 > 5000:
                    name = f"ext_warm_r{g_ratio:.1f}b{b_ratio:.1f}_{base_q16}"
                    patches.append({
                        'name': name,
                        'r16': r16,
                        'g16': g16,
                        'b16': b16,
                        'w16': 0
                    })

    # Warm RGB+W variants for highlight-preserving yellows/oranges/pinks.
    warm_white_bases = [
        (1.00, 0.45, 0.05),  # deep orange-white
        (1.00, 0.60, 0.10),  # orange-yellow white
        (1.00, 0.75, 0.15),  # rich warm yellow
        (1.00, 0.85, 0.25),  # bright amber
        (1.00, 0.55, 0.40),  # warm pink-orange
        (1.00, 0.45, 0.60),  # warm pink-magenta
    ]
    for base_q16 in [10000, 14000, 18000, 22000, 26000, 30000, 34000, 38000, 42000, 48000, 54000, 60000]:
        for r_ratio, g_ratio, b_ratio in warm_white_bases:
            for white_ratio in [0.15, 0.30, 0.45, 0.60]:
                r16 = min(65535, int(base_q16 * r_ratio))
                g16 = min(65535, int(base_q16 * g_ratio))
                b16 = min(65535, int(base_q16 * b_ratio))
                w16 = min(65535, int(base_q16 * white_ratio))
                if r16 > 5000 and w16 > 1000:
                    name = (
                        f"ext_warmw_r{r_ratio:.2f}g{g_ratio:.2f}b{b_ratio:.2f}"
                        f"_q{base_q16}_w{int(white_ratio * 100)}"
                    )
                    patches.append({
                        'name': name,
                        'r16': r16,
                        'g16': g16,
                        'b16': b16,
                        'w16': w16,
                    })

    # Neon/beam-specific high-white warm set (sunset neons, warm signage, pink highlights).
    neon_warm_hues = [
        (1.00, 0.40, 0.08),
        (1.00, 0.58, 0.18),
        (1.00, 0.72, 0.28),
        (1.00, 0.48, 0.55),
    ]
    for base_rgb_q16 in [10000, 14000, 18000, 22000, 28000]:
        for r_ratio, g_ratio, b_ratio in neon_warm_hues:
            for white_q16 in [12000, 18000, 24000, 30000, 36000]:
                r16 = min(65535, int(base_rgb_q16 * r_ratio))
                g16 = min(65535, int(base_rgb_q16 * g_ratio))
                b16 = min(65535, int(base_rgb_q16 * b_ratio))
                w16 = min(65535, int(white_q16))
                name = (
                    f"ext_warm_neon_r{r_ratio:.2f}g{g_ratio:.2f}b{b_ratio:.2f}"
                    f"_rgb{base_rgb_q16}_w{white_q16}"
                )
                patches.append({
                    'name': name,
                    'r16': r16,
                    'g16': g16,
                    'b16': b16,
                    'w16': w16,
                })
    
    return patches


def generate_cool_saturation_batch():
    """Extended cool colors with both chromatic and RGB+W variants.

    Includes:
    - RGB-only cool hues (cyan/light blue/magenta family)
    - Blue-white and neon-like cool variants using white channel
      for content such as lightsabers, neon, and bright cyan highlights.
    """
    patches = []

    # Target q16 ranges for chromatic cool midtones and highlights (RGB-only baseline).
    for base_q16 in [8000, 12000, 16000, 20000, 24000, 28000, 32000, 36000, 40000, 45000, 50000, 55000, 60000]:
        # Cyan: blue + green, varying red (magenta tint).
        for r_ratio in [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]:
            for g_ratio in [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
                r16 = min(65535, int(base_q16 * r_ratio))
                g16 = min(65535, int(base_q16 * g_ratio))
                b16 = min(65535, int(base_q16 * 1.0))

                if b16 > 5000:
                    name = f"ext_cool_r{r_ratio:.1f}g{g_ratio:.1f}_{base_q16}"
                    patches.append({
                        'name': name,
                        'r16': r16,
                        'g16': g16,
                        'b16': b16,
                        'w16': 0,
                    })

    # RGB+W cool variants for blue-white highlights and neon-like rendering.
    cool_white_bases = [
        (0.05, 0.45, 1.0),  # deep blue-white
        (0.10, 0.60, 1.0),  # cyan-white
        (0.20, 0.80, 1.0),  # bright cyan-blue
        (0.30, 0.85, 1.0),  # light cyan-blue
        (0.35, 0.95, 1.0),  # ice-blue
        (0.45, 1.00, 1.0),  # near-neutral cool white
    ]
    for base_q16 in [10000, 14000, 18000, 22000, 26000, 30000, 34000, 38000, 42000, 48000, 54000, 60000]:
        for r_ratio, g_ratio, b_ratio in cool_white_bases:
            for white_ratio in [0.15, 0.30, 0.45, 0.60]:
                r16 = min(65535, int(base_q16 * r_ratio))
                g16 = min(65535, int(base_q16 * g_ratio))
                b16 = min(65535, int(base_q16 * b_ratio))
                w16 = min(65535, int(base_q16 * white_ratio))
                if b16 > 4000 and w16 > 1000:
                    name = (
                        f"ext_coolw_r{r_ratio:.2f}g{g_ratio:.2f}b{b_ratio:.2f}"
                        f"_q{base_q16}_w{int(white_ratio * 100)}"
                    )
                    patches.append({
                        'name': name,
                        'r16': r16,
                        'g16': g16,
                        'b16': b16,
                        'w16': w16,
                    })

    # Neon/beam-specific high-white cool set (lightsaber/neon signage style).
    neon_cool_hues = [
        (0.08, 0.55, 1.0),
        (0.12, 0.70, 1.0),
        (0.20, 0.90, 1.0),
        (0.35, 1.00, 1.0),
    ]
    for base_rgb_q16 in [10000, 14000, 18000, 22000, 28000]:
        for r_ratio, g_ratio, b_ratio in neon_cool_hues:
            for white_q16 in [12000, 18000, 24000, 30000, 36000]:
                r16 = min(65535, int(base_rgb_q16 * r_ratio))
                g16 = min(65535, int(base_rgb_q16 * g_ratio))
                b16 = min(65535, int(base_rgb_q16 * b_ratio))
                w16 = min(65535, int(white_q16))
                name = (
                    f"ext_cool_neon_r{r_ratio:.2f}g{g_ratio:.2f}b{b_ratio:.2f}"
                    f"_rgb{base_rgb_q16}_w{white_q16}"
                )
                patches.append({
                    'name': name,
                    'r16': r16,
                    'g16': g16,
                    'b16': b16,
                    'w16': w16,
                })

    return patches


def generate_skin_tones_batch():
    """Skin tones, browns, tans, maroons: NOW using WHITE CHANNEL for proper tone preservation.
    
    Key insight: Brown/tan is (R=1.0, G=0.5, B=0.25, W=brightness_add).
    Adding brightness via W keeps the warm RGB ratio constant instead of desaturating toward gray.
    """
    patches = []
    
    # Skin tone / brown RGB base ratios (these stay constant, we vary brightness via W)
    skin_bases = [
        (1.0, 0.7, 0.5),   # Light tan/peach
        (1.0, 0.65, 0.45),
        (1.0, 0.6, 0.4),   # Mid tan
        (1.0, 0.55, 0.35),
        (1.0, 0.5, 0.3),   # Deep tan/brown
        (0.95, 0.6, 0.35), # Red-brown
        (0.9, 0.5, 0.3),   # Maroon-ish
        (0.85, 0.45, 0.25),
        (1.0, 0.75, 0.6),  # Very light tan (close to peach)
        (1.0, 0.8, 0.7),   # Lighter, skin-tone
    ]
    
    # Apply across brightness levels, but now use WHITE CHANNEL to add brightness
    # This way RGB ratio stays constant (preserving warmth/tone) while brightness increases
    for base_rgb_q16 in [4000, 6000, 8000, 10000, 12000]:  # Base RGB values (constant)
        for white_add_q16 in [2000, 6000, 10000, 14000, 18000, 22000, 26000, 30000]:  # White channel additions
            for r_ratio, g_ratio, b_ratio in skin_bases:
                r16 = min(65535, int(base_rgb_q16 * r_ratio))
                g16 = min(65535, int(base_rgb_q16 * g_ratio))
                b16 = min(65535, int(base_rgb_q16 * b_ratio))
                w16 = min(65535, int(white_add_q16))
                
                if r16 > 1000 and w16 > 500:  # Only if meaningful color + white content
                    name = f"skin_w{r_ratio:.2f}g{g_ratio:.2f}b{b_ratio:.2f}_rgb{base_rgb_q16}_w{white_add_q16}"
                    patches.append({
                        'name': name,
                        'r16': r16,
                        'g16': g16,
                        'b16': b16,
                        'w16': w16
                    })
    
    return patches


def generate_gray_ramp_whitechannel_batch():
    """Gray ramp covering both RGB-only and RGB+W combinations.

    Critical for neutral tracking, white balance, and highlight character.
    """
    patches = []

    # Baseline neutral ramp without white.
    for gray_q16 in range(1000, 65000, 2000):
        q = min(65535, int(gray_q16))
        patches.append({
            'name': f"gray_rgb_only_{gray_q16}",
            'r16': q,
            'g16': q,
            'b16': q,
            'w16': 0,
        })

    # RGB + white variants to study neutral shifts when white channel participates.
    for base_rgb_q16 in [2000, 5000, 8000, 12000, 16000, 20000, 24000, 28000, 32000, 40000, 50000, 60000]:
        for white_q16 in [5000, 10000, 15000, 20000, 25000, 30000, 35000, 40000]:
            q = min(65535, int(base_rgb_q16))
            w16 = min(65535, int(white_q16))
            patches.append({
                'name': f"gray_rgb_white_rgb{base_rgb_q16}_w{white_q16}",
                'r16': q,
                'g16': q,
                'b16': q,
                'w16': w16,
            })

    return patches


def generate_pastel_batch():
    """Balanced pastel batch: higher RGB, gentle white mix, more color presence for projection on grayish wall."""
    patches = []
    # Pastel hue bases: soft, light, but with more color presence
    pastel_hues = [
        (1.0, 0.6, 0.7),   # Pastel pink
        (1.0, 0.8, 0.6),   # Pastel peach
        (1.0, 1.0, 0.7),   # Pastel yellow
        (0.7, 1.0, 0.7),   # Pastel lime
        (0.6, 1.0, 0.8),   # Pastel mint
        (0.6, 0.8, 1.0),   # Pastel sky blue
        (0.8, 0.6, 1.0),   # Pastel lavender
        (1.0, 0.6, 0.9),   # Pastel magenta
        (0.9, 0.9, 0.9),   # Pastel gray (near white)
    ]
    # Higher RGB base values for more color presence
    for base_rgb_q16 in [12000, 18000, 24000, 32000, 40000]:
        for r_ratio, g_ratio, b_ratio in pastel_hues:
            r16 = min(65535, int(base_rgb_q16 * r_ratio))
            g16 = min(65535, int(base_rgb_q16 * g_ratio))
            b16 = min(65535, int(base_rgb_q16 * b_ratio))
            # RGB only (no white)
            name = f"pastel_rgb_r{r_ratio:.2f}g{g_ratio:.2f}b{b_ratio:.2f}_{base_rgb_q16}"
            patches.append({'name': name, 'r16': r16, 'g16': g16, 'b16': b16, 'w16': 0})
            # Gentle white mixes: a few levels, leaning into white but not overwhelming
            for white_ratio in [0.10, 0.20, 0.35, 0.50]:
                w16 = min(65535, int(base_rgb_q16 * white_ratio))
                if w16 > 500:
                    name = f"pastel_rgbw_r{r_ratio:.2f}g{g_ratio:.2f}b{b_ratio:.2f}_q{base_rgb_q16}_w{int(white_ratio*100)}"
                    patches.append({'name': name, 'r16': r16, 'g16': g16, 'b16': b16, 'w16': w16})
    return patches


def generate_white_channel_focus_batch():
    """Dedicated batch for white channel combinations with warm RGB base.
    Tests how white mixing affects perceived tone across the spectrum."""
    patches = []
    
    # RGB bases that form warm tones (without white, just to show the baseline)
    warm_rgb_ratios = [
        (1.0, 0.7, 0.5),   # Peachy tan
        (1.0, 0.6, 0.4),   # Medium brown
        (1.0, 0.5, 0.3),   # Deep brown
        (1.0, 0.5, 0.0),   # Deep orange
    ]
    
    for r_ratio, g_ratio, b_ratio in warm_rgb_ratios:
        # Test various white levels with fixed warm RGB
        base_rgb = 12000
        for white_q16 in [0, 5000, 10000, 15000, 20000, 25000, 30000, 35000, 40000, 45000, 50000]:
            r16 = min(65535, int(base_rgb * r_ratio))
            g16 = min(65535, int(base_rgb * g_ratio))
            b16 = min(65535, int(base_rgb * b_ratio))
            w16 = min(65535, int(white_q16))
            
            name = f"white_r{r_ratio:.1f}g{g_ratio:.1f}b{b_ratio:.1f}_w{white_q16}"
            patches.append({
                'name': name,
                'r16': r16,
                'g16': g16,
                'b16': b16,
                'w16': w16
            })
    
    return patches


def generate_high_saturation_edges_batch():
    """Extreme saturation/brightness combinations: primary/secondary colors at edges.
    Uses small white channel additions to avoid clipping while maintaining saturation."""
    patches = []
    
    # Highly saturated primary/secondary colors
    saturated_colors = [
        (1.0, 0.0, 0.0),   # Pure red
        (1.0, 1.0, 0.0),   # Pure yellow
        (0.0, 1.0, 0.0),   # Pure green
        (0.0, 1.0, 1.0),   # Pure cyan
        (0.0, 0.0, 1.0),   # Pure blue
        (1.0, 0.0, 1.0),   # Pure magenta
        (1.0, 0.5, 0.0),   # Orange
        (0.5, 1.0, 0.0),   # Lime
        (0.0, 1.0, 0.5),   # Spring green
        (0.0, 0.5, 1.0),   # Sky blue
        (0.5, 0.0, 1.0),   # Violet
        (1.0, 0.0, 0.5),   # Rose
    ]
    
    for brightness_q16 in [15000, 20000, 25000, 30000, 35000, 40000, 45000, 50000, 55000, 60000]:
        for r_ratio, g_ratio, b_ratio in saturated_colors:
            r16 = min(65535, int(brightness_q16 * r_ratio))
            g16 = min(65535, int(brightness_q16 * g_ratio))
            b16 = min(65535, int(brightness_q16 * b_ratio))
            
            # Also add lower saturation variants with white channel to maintain tone while brightening
            for sat_factor in [0.5, 0.75]:
                for white_add in [0, 5000, 10000]:
                    r16_sat = min(65535, int(brightness_q16 * (1.0 - sat_factor + sat_factor * r_ratio)))
                    g16_sat = min(65535, int(brightness_q16 * (1.0 - sat_factor + sat_factor * g_ratio)))
                    b16_sat = min(65535, int(brightness_q16 * (1.0 - sat_factor + sat_factor * b_ratio)))
                    w16 = min(65535, int(white_add))
                    
                    name = f"hisaturat_sat{sat_factor:.2f}_w{white_add}_{r_ratio:.1f}g{g_ratio:.1f}b{b_ratio:.1f}_{brightness_q16}"
                    patches.append({
                        'name': name,
                        'r16': r16_sat,
                        'g16': g16_sat,
                        'b16': b16_sat,
                        'w16': w16
                    })
    
    return patches


def generate_secondary_color_batch():
    """Secondary colors (yellow, cyan, magenta) and their white-mix variants."""
    patches = []
    secondary_colors = [
        (1.0, 1.0, 0.0),  # Yellow
        (0.0, 1.0, 1.0),  # Cyan
        (1.0, 0.0, 1.0),  # Magenta
    ]
    for base_q16 in [8000, 12000, 16000, 20000, 24000, 28000, 32000, 36000, 40000, 45000, 50000, 55000, 60000]:
        for r, g, b in secondary_colors:
            r16 = min(65535, int(base_q16 * r))
            g16 = min(65535, int(base_q16 * g))
            b16 = min(65535, int(base_q16 * b))
            name = f"secondary_rgb_r{r:.1f}g{g:.1f}b{b:.1f}_{base_q16}"
            patches.append({'name': name, 'r16': r16, 'g16': g16, 'b16': b16, 'w16': 0})
            for white_ratio in [0.15, 0.30, 0.45, 0.60]:
                w16 = min(65535, int(base_q16 * white_ratio))
                if w16 > 1000:
                    name = f"secondary_rgbw_r{r:.1f}g{g:.1f}b{b:.1f}_q{base_q16}_w{int(white_ratio*100)}"
                    patches.append({'name': name, 'r16': r16, 'g16': g16, 'b16': b16, 'w16': w16})
    return patches


def generate_tertiary_color_batch():
    """Tertiary colors (orange, chartreuse, spring green, azure, violet, rose) and their white-mix variants."""
    patches = []
    tertiary_colors = [
        (1.0, 0.5, 0.0),   # Orange
        (0.5, 1.0, 0.0),   # Chartreuse
        (0.0, 1.0, 0.5),   # Spring green
        (0.0, 0.5, 1.0),   # Azure
        (0.5, 0.0, 1.0),   # Violet
        (1.0, 0.0, 0.5),   # Rose
    ]
    for base_q16 in [8000, 12000, 16000, 20000, 24000, 28000, 32000, 36000, 40000, 45000, 50000, 55000, 60000]:
        for r, g, b in tertiary_colors:
            r16 = min(65535, int(base_q16 * r))
            g16 = min(65535, int(base_q16 * g))
            b16 = min(65535, int(base_q16 * b))
            name = f"tertiary_rgb_r{r:.1f}g{g:.1f}b{b:.1f}_{base_q16}"
            patches.append({'name': name, 'r16': r16, 'g16': g16, 'b16': b16, 'w16': 0})
            for white_ratio in [0.15, 0.30, 0.45, 0.60]:
                w16 = min(65535, int(base_q16 * white_ratio))
                if w16 > 1000:
                    name = f"tertiary_rgbw_r{r:.1f}g{g:.1f}b{b:.1f}_q{base_q16}_w{int(white_ratio*100)}"
                    patches.append({'name': name, 'r16': r16, 'g16': g16, 'b16': b16, 'w16': w16})
    return patches


def generate_brown_tan_profile_batch():
    """Comprehensive brown & tan profile, including deep-red browns and wide brownlike swathes, with white mixes."""
    patches = []
    # Brown/tan base ratios: covers classic brown, tan, reddish-brown, ochre, sienna, umber, etc.
    brown_bases = [
        (1.00, 0.60, 0.30),  # classic brown
        (1.00, 0.50, 0.20),  # deep brown
        (0.90, 0.45, 0.18),  # dark brown
        (0.85, 0.40, 0.15),  # very deep brown
        (1.00, 0.70, 0.40),  # tan
        (1.00, 0.80, 0.55),  # light tan
        (1.00, 0.65, 0.35),  # ochre
        (0.95, 0.55, 0.25),  # reddish brown
        (0.80, 0.35, 0.10),  # umber
        (0.90, 0.30, 0.10),  # burnt umber
        (1.00, 0.55, 0.15),  # sienna
        (1.00, 0.45, 0.10),  # deep sienna
        (0.85, 0.30, 0.08),  # espresso
        (1.00, 0.75, 0.50),  # sand
        (1.00, 0.85, 0.65),  # pale sand
        (0.95, 0.40, 0.20),  # mahogany
        (0.80, 0.25, 0.05),  # very dark brown
        (1.00, 0.60, 0.45),  # coppery tan
        (1.00, 0.55, 0.30),  # chestnut
        (0.90, 0.50, 0.25),  # russet
    ]
    # Wide range of base brightness for deep to light browns
    for base_rgb_q16 in [3000, 5000, 8000, 12000, 16000, 20000, 26000, 32000, 40000]:
        for r_ratio, g_ratio, b_ratio in brown_bases:
            r16 = min(65535, int(base_rgb_q16 * r_ratio))
            g16 = min(65535, int(base_rgb_q16 * g_ratio))
            b16 = min(65535, int(base_rgb_q16 * b_ratio))
            # RGB only (no white)
            name = f"brown_rgb_r{r_ratio:.2f}g{g_ratio:.2f}b{b_ratio:.2f}_{base_rgb_q16}"
            patches.append({'name': name, 'r16': r16, 'g16': g16, 'b16': b16, 'w16': 0})
            # White mixes: add white channel to brighten while preserving brown ratio
            for white_ratio in [0.10, 0.20, 0.30, 0.40, 0.55, 0.70]:
                w16 = min(65535, int(base_rgb_q16 * white_ratio))
                if w16 > 500:
                    name = f"brown_rgbw_r{r_ratio:.2f}g{g_ratio:.2f}b{b_ratio:.2f}_q{base_rgb_q16}_w{int(white_ratio*100)}"
                    patches.append({'name': name, 'r16': r16, 'g16': g16, 'b16': b16, 'w16': w16})
    return patches


def generate_yellow_orange_batch():
    """Yellow/orange batch: wide range from green-leaning yellow to deep red orange, with RGB & RGBW passes."""
    patches = []
    # Define a gradient from greenish yellow to deep red orange
    # (r, g, b) covers: green-yellow -> pure yellow -> orange -> deep orange -> red-orange
    yellow_orange_hues = [
        (0.85, 1.0, 0.0),   # greenish yellow
        (0.95, 1.0, 0.0),   # yellow-green
        (1.0, 1.0, 0.0),    # pure yellow
        (1.0, 0.90, 0.0),   # warm yellow
        (1.0, 0.80, 0.0),   # yellow-orange
        (1.0, 0.65, 0.0),   # orange
        (1.0, 0.50, 0.0),   # deep orange
        (1.0, 0.35, 0.0),   # red-orange
        (1.0, 0.20, 0.0),   # deep red-orange
    ]
    # Use a moderate number of brightness levels to keep patch count in target range
    for base_rgb_q16 in [10000, 14000, 18000, 22000, 26000, 30000, 34000, 38000, 42000, 48000, 54000, 60000]:
        for r_ratio, g_ratio, b_ratio in yellow_orange_hues:
            r16 = min(65535, int(base_rgb_q16 * r_ratio))
            g16 = min(65535, int(base_rgb_q16 * g_ratio))
            b16 = min(65535, int(base_rgb_q16 * b_ratio))
            # RGB only
            name = f"yelloworange_rgb_r{r_ratio:.2f}g{g_ratio:.2f}b{b_ratio:.2f}_{base_rgb_q16}"
            patches.append({'name': name, 'r16': r16, 'g16': g16, 'b16': b16, 'w16': 0})
            # RGBW passes: a few white levels, not overwhelming
            for white_ratio in [0.10, 0.22, 0.35, 0.50]:
                w16 = min(65535, int(base_rgb_q16 * white_ratio))
                if w16 > 500:
                    name = f"yelloworange_rgbw_r{r_ratio:.2f}g{g_ratio:.2f}b{b_ratio:.2f}_q{base_rgb_q16}_w{int(white_ratio*100)}"
                    patches.append({'name': name, 'r16': r16, 'g16': g16, 'b16': b16, 'w16': w16})
    return patches


def generate_bright_yellow_orange_batch():
    """Bright yellow/orange and super-saturated pass: high RGB, RGBW, covers green-yellow to deep orange, 500-600 samples."""
    patches = []
    # More granular hues for denser coverage
    hues = [
        (0.90, 1.0, 0.0), (0.95, 1.0, 0.0), (1.0, 1.0, 0.0), (1.0, 0.95, 0.0),
        (1.0, 0.85, 0.0), (1.0, 0.75, 0.0), (1.0, 0.70, 0.0), (1.0, 0.60, 0.0),
        (1.0, 0.55, 0.0), (1.0, 0.45, 0.0), (1.0, 0.35, 0.0), (1.0, 0.25, 0.0),
        (1.0, 0.20, 0.0), (1.0, 0.10, 0.0)
    ]
    # More brightness levels
    rgb_bases = [42000, 46000, 50000, 54000, 58000, 62000, 65535]
    # More white ratios for RGBW variants
    white_ratios = [0.0, 0.07, 0.14, 0.22, 0.28, 0.35, 0.42]
    for base in rgb_bases:
        for r, g, b in hues:
            for w_ratio in white_ratios:
                r16 = min(65535, int(base * r))
                g16 = min(65535, int(base * g))
                b16 = min(65535, int(base * b))
                w16 = min(65535, int(base * w_ratio))
                if w16 == 0:
                    name = f"brightyo_rgb_r{r:.2f}g{g:.2f}b{b:.2f}_{base}"
                else:
                    name = f"brightyo_rgbw_r{r:.2f}g{g:.2f}b{b:.2f}_{base}_w{int(w_ratio*100)}"
                patches.append({'name': name, 'r16': r16, 'g16': g16, 'b16': b16, 'w16': w16})
    # Super-saturated: max out one or two channels, minimal white
    supersat = [
        (1.0, 1.0, 0.0), (1.0, 0.95, 0.0), (1.0, 0.85, 0.0), (1.0, 0.70, 0.0),
        (1.0, 0.55, 0.0), (1.0, 0.20, 0.0), (1.0, 0.0, 0.0)
    ]
    for base in [60000, 65535]:
        for r, g, b in supersat:
            for w16 in [0, 1000, 2000, 4000, 7000]:
                name = f"supersatyo_rgbw_r{r:.2f}g{g:.2f}b{b:.2f}_{base}_w{w16}"
                patches.append({'name': name, 'r16': min(65535, int(base*r)), 'g16': min(65535, int(base*g)), 'b16': min(65535, int(base*b)), 'w16': w16})
    return patches


def generate_edge_case_colors_batch():
    """Expanded edge-case color batch: deep/dark, muddy, extreme white-tint, off-axis, high-brightness, and in-between colors, with W variants for muddy/deep."""
    patches = []
    # 1. Very deep/dark colors (low RGB, low/zero white, now with W variants)
    deep_colors = [
        (0.08, 0.08, 0.20), (0.10, 0.20, 0.10), (0.20, 0.08, 0.08), (0.15, 0.12, 0.10),
        (0.12, 0.10, 0.18), (0.18, 0.12, 0.10), (0.10, 0.18, 0.12), (0.16, 0.09, 0.13),
    ]
    for base in [1200, 2500, 4000, 6000, 9000, 12000]:
        for r, g, b in deep_colors:
            r16 = int(base * r)
            g16 = int(base * g)
            b16 = int(base * b)
            patches.append({'name': f'edge_deep_rgb_{r:.2f}_{g:.2f}_{b:.2f}_{base}', 'r16': r16, 'g16': g16, 'b16': b16, 'w16': 0})
            for w_ratio in [0.10, 0.22, 0.35]:
                w16 = int(base * w_ratio)
                if w16 > 0:
                    patches.append({'name': f'edge_deep_rgbw_{r:.2f}_{g:.2f}_{b:.2f}_{base}_w{int(w_ratio*100)}', 'r16': r16, 'g16': g16, 'b16': b16, 'w16': w16})

    # 2. Muddy/desaturated colors (all RGB nonzero, not gray, with W variants)
    muddy_colors = [
        (0.35, 0.30, 0.18), (0.28, 0.32, 0.38), (0.40, 0.36, 0.32), (0.22, 0.38, 0.36),
        (0.32, 0.28, 0.40), (0.38, 0.22, 0.36), (0.36, 0.40, 0.32), (0.30, 0.35, 0.28),
    ]
    for base in [6000, 9000, 12000, 18000, 24000, 32000]:
        for r, g, b in muddy_colors:
            r16 = int(base * r)
            g16 = int(base * g)
            b16 = int(base * b)
            patches.append({'name': f'edge_muddy_rgb_{r:.2f}_{g:.2f}_{b:.2f}_{base}', 'r16': r16, 'g16': g16, 'b16': b16, 'w16': 0})
            for w_ratio in [0.10, 0.22, 0.35]:
                w16 = int(base * w_ratio)
                if w16 > 0:
                    patches.append({'name': f'edge_muddy_rgbw_{r:.2f}_{g:.2f}_{b:.2f}_{base}_w{int(w_ratio*100)}', 'r16': r16, 'g16': g16, 'b16': b16, 'w16': w16})

    # 3. Extreme white-dominant tints (white >> RGB)
    tint_colors = [
        (0.10, 0.10, 0.18), (0.18, 0.10, 0.10), (0.10, 0.18, 0.10), (0.15, 0.12, 0.18), (0.18, 0.15, 0.12),
    ]
    for base in [2000, 4000, 6000, 9000]:
        for r, g, b in tint_colors:
            for w in [12000, 20000, 32000, 40000]:
                patches.append({'name': f'edge_tint_rgbw_{r:.2f}_{g:.2f}_{b:.2f}_{base}_w{w}', 'r16': int(base*r), 'g16': int(base*g), 'b16': int(base*b), 'w16': w})

    # 4. Off-axis color ratios (not on primary/secondary/tertiary lines)
    off_axis = [
        (0.7, 0.2, 0.6), (0.3, 0.7, 0.5), (0.5, 0.3, 0.7), (0.6, 0.6, 0.2),
        (0.4, 0.7, 0.3), (0.2, 0.4, 0.7), (0.7, 0.4, 0.2), (0.5, 0.5, 0.5),
    ]
    for base in [9000, 12000, 18000, 24000, 32000, 40000]:
        for r, g, b in off_axis:
            patches.append({'name': f'edge_offaxis_rgb_{r:.2f}_{g:.2f}_{b:.2f}_{base}', 'r16': int(base*r), 'g16': int(base*g), 'b16': int(base*b), 'w16': 0})

    # 5. High-brightness, high-saturation (RGB near max, little/no white)
    for r, g, b in [(1.0, 0.7, 0.2), (0.8, 1.0, 0.1), (0.1, 0.8, 1.0), (1.0, 0.1, 0.8), (0.9, 0.9, 0.2), (0.2, 0.9, 0.9)]:
        for base in [48000, 54000, 60000]:
            patches.append({'name': f'edge_highbright_rgb_{r:.2f}_{g:.2f}_{b:.2f}_{base}', 'r16': int(base*r), 'g16': int(base*g), 'b16': int(base*b), 'w16': 0})

    # 6. In-betweeners (between brown/olive, pastel/gray, etc.)
    inbetween = [
        (0.55, 0.45, 0.25), (0.80, 0.80, 0.70), (0.60, 0.50, 0.40), (0.40, 0.60, 0.55),
        (0.65, 0.55, 0.35), (0.75, 0.75, 0.60), (0.50, 0.60, 0.50), (0.60, 0.50, 0.60),
    ]
    for base in [9000, 12000, 18000, 24000, 32000, 40000]:
        for r, g, b in inbetween:
            for w in [0, 2000, 4000, 9000]:
                patches.append({'name': f'edge_inbetween_rgbw_{r:.2f}_{g:.2f}_{b:.2f}_{base}_w{w}', 'r16': int(base*r), 'g16': int(base*g), 'b16': int(base*b), 'w16': w})
    return patches


def generate_white_mix_orange_peach_batch():
    """White-mix orange/peach/coral: high R, moderate G, low B, wide W, 400-600 samples."""
    patches = []
    # Orange/peach/coral hues (R high, G moderate, B low)
    hues = [
        (1.0, 0.55, 0.0),   # classic orange
        (1.0, 0.45, 0.0),   # deep orange
        (1.0, 0.65, 0.10),  # peach
        (1.0, 0.55, 0.15),  # coral
        (1.0, 0.60, 0.20),  # light coral
        (1.0, 0.50, 0.10),  # deep peach
        (1.0, 0.40, 0.10),  # deep coral
        (1.0, 0.70, 0.20),  # pale peach
        (1.0, 0.60, 0.05),  # orange-white
    ]
    # Brightness levels (focus on high, but include some mid-high)
    rgb_bases = [18000, 24000, 32000, 40000, 48000, 54000, 60000, 65535]
    # White ratios (wide range, up to 70%)
    white_ratios = [0.10, 0.18, 0.26, 0.34, 0.42, 0.50, 0.58, 0.66, 0.74]
    for base in rgb_bases:
        for r, g, b in hues:
            for w_ratio in white_ratios:
                r16 = min(65535, int(base * r))
                g16 = min(65535, int(base * g))
                b16 = min(65535, int(base * b))
                w16 = min(65535, int(base * w_ratio))
                name = f"whitemix_orangepeach_r{r:.2f}g{g:.2f}b{b:.2f}_{base}_w{int(w_ratio*100)}"
                patches.append({'name': name, 'r16': r16, 'g16': g16, 'b16': b16, 'w16': w16})
    return patches


def export_batch(patches, batch_name, base_dir=Path('patch_plans')):
    """Export a batch to CSV."""
    base_dir = Path(base_dir)
    base_dir.mkdir(exist_ok=True)
    
    out_path = base_dir / f"patch_plan_batch_{batch_name}.csv"
    
    with open(out_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['name', 'r16', 'g16', 'b16', 'w16'])
        writer.writeheader()
        for patch in patches:
            writer.writerow(patch)
    
    print(f"Exported {len(patches)} patches to {out_path}")
    return out_path


def main():
    batches = [
        ('extended_warm_saturations', generate_warm_saturation_batch()),
        ('extended_cool_saturations', generate_cool_saturation_batch()),
        ('secondary_colors', generate_secondary_color_batch()),
        ('tertiary_colors', generate_tertiary_color_batch()),
        ('skin_tones_and_browns_whitechannel', generate_skin_tones_batch()),
        ('gray_ramp_whitechannel', generate_gray_ramp_whitechannel_batch()),
        ('pastels', generate_pastel_batch()),
        ('white_channel_focus', generate_white_channel_focus_batch()),
        ('high_saturation_edges', generate_high_saturation_edges_batch()),
        ('brown_tan_profile', generate_brown_tan_profile_batch()),
        ('yellow_orange_batch', generate_yellow_orange_batch()),
        ('bright_yellow_orange', generate_bright_yellow_orange_batch()),
        ('edge_case_colors', generate_edge_case_colors_batch()),
        ('white_mix_orange_peach', generate_white_mix_orange_peach_batch()),
    ]
    
    for batch_name, patches in batches:
        export_batch(patches, batch_name)
    
    print("\nBatch summary:")
    for batch_name, patches in batches:
        print(f"  {batch_name}: {len(patches)} patches")


if __name__ == '__main__':
    main()
