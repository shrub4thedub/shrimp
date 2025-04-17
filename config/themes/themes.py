"""
themes.py

Holds the built-in Shrimp themes in a Python dictionary form. 
Any additional .py files in this directory that define `theme_data` and `theme_name`
will also be auto-detected and included.
"""

def get_builtin_themes():
    """
    Returns a dict mapping built-in theme names to their color definitions.
    These are the default Shrimp themes: boring, shrimp, catpuccin.
    """
    return {
        "boring": {
            "bg": (40, 42, 54),
            "fg": (248, 248, 242),
            "sel": (68, 71, 90),
            "accent": (98, 114, 164),
            "ft_bg": (51, 54, 71),
            "sidebar": (52, 55, 70),
            "highlight": (52, 55, 70),
        },
        "shrimp": {
            "bg": (30, 30, 30),
            "fg": (250, 240, 230),
            "sel": (80, 60, 50),
            "accent": (255, 165, 125),
            "ft_bg": (45, 40, 35),
            "sidebar": (50, 45, 40),
            "highlight": (50, 45, 40),
        },
        "catpuccin": {
            "bg": (30, 30, 46),
            "fg": (205, 214, 244),
            "sel": (69, 71, 90),
            "accent": (137, 180, 250),
            "ft_bg": (49, 50, 68),
            "sidebar": (24, 24, 37),
            "highlight": (69, 71, 90),
        },
    }

