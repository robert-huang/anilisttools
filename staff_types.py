"""Categorize staff roles by genre.

Note that staff roles often have a (ep N) or (OP/ED) suffix which should be removed."""

# Words that can be omitted without losing the gist of which production area they're in, if they're not the only word
# things like 'of' are included to trim e.g. "Director of Photography" -> "Photography"
# TODO: 'Original' and/or 'Production' too, maybe
ignorable_keywords = {"of", "Chief", "Director", "Executive", "Producer", "Supervisor", "Manager", "Main", "Desk",
                      "Assistant", "Assistance", "Associate", "Engineer"}

theme_songs = {"Theme Song", "Theme Song Performance", "Theme Song Composition", "Theme Song Arrangement"}
ost = {"Music", "Music Production", "Music Selection",
       "Insert Song Composition", "Insert Song Arrangement", "Insert Song Performance", "Background Music Singing"}
music = theme_songs | ost

sound = {"Sound", "Sound Design", "Sound Mixing", "Sound Adjustment", "Sound Production",
         "Sound Effects", "Foley",
         "Recording", "Recording Adjustment", "ADR Mixing", "ADR Recording"}
audio = music | sound

art = {"Art", "Art Design", "Art Board", "Illustration", "Concept Art",
       "Design", "Character Design", "Original Character Design", "Sub Character Design", "Costume Design",
       "Editing", "Layout",
       "Color Design", "Color Coordination", "Coloring",
       "Finishing", "Finishing Production", "Finishing Check", "Cel Finishing Check",
       "Background Art", "Background Art Production", "Paint",
       "Photography", "Photography Production",
       "2D Works", "2D Digital Corrector",
       "CG", "CG Modeling", "CG Production", "CG Modeling", "CG Sub Modeling", "CG Design", "CG Rigging", "CG Setup",
       "CG Background Art", "CG Assets",
       "3D Works", "3DCG", "Special Effects", "Monitor Graphics",
       "Technical", "Technical Artist", "Mechanical Coordinator",
       "Production Design", "Design Works", "Mechanical Design", "Prop Design", "World Design", "Weapon Design",
       "Creature Design", "Monster Design", "Eyecatch Illustration", "Endcard"}
animation = {"Layout Design",
             "Animator", "Animation", "Key Animation", "2nd Key Animation",
             "In-Between Animation", "In-Betweens", "In-Betweens Production", "In-Betweens Check",
             "CG Animation", "Digital Animation", "Action Animation", "Effects", "Effects Animation",
             "Character Animation", "Special Animation", "Weapon Animation", "Mechanical Animation",
             "Mechanical Animator", "Creature Animation", "Eyecatch Animation"}
visuals = art | animation

writing = {"Original Story", "Original Creator", "Original Concept",
           "Series Composition", "Script", "Script Composition", "Storyboard", "Leica Reel"}

# "Episode" for the trimmed result of "Episode Director" etc.
directing = {"Director", "Episode", "Unit", "Planning", "Co-Planning", "Action", "Technical"}

marketing = {"Title Logo Design", "PV Production", "Video Editing", "Online Editing", "Web Design",
             "Website Production", "Preview", "Videogram Production",
             "Advertising", "Advertising Design", "Program Advertising", "Publicity", "Sales Promotion",
             "Web Promotion", "Public Relations",
             "License", "Distribution License", "Domestic License", "Domestic Distribution", "Overseas License",
             "Overseas Sales"}

misc = {"Producer", "Production", "Supervisor", "Assistance", "Organization",  # E.g. Production Desk
        "Casting",
        "Production Generalization", "Production Office", "Production Committee", "Package", "Lab Coordinator",
        "Studio Coordination", "Brush Design", "Monitor Work",
        "ADR", "ADR Script", "ADR Prep",  # Dub
        "Insert Song Lyrics", "Theme Song Lyrics"}  # sorry I'm not counting lyrics

all_ = audio | visuals | writing | directing | marketing | misc


def trim_role(role: str):
    """Given a production staff role, trim any words/info from it that don't aid in classifying its staff type.
    This includes:
    - Dropping trailing parentheticals (e.g. "Storyboards (ep 1, 3)" -> "Storyboards").
    - Dropping semantically meaningless words (e.g. "Chief X", "Assistant X" -> "X"), unless this would remove all
      words, in which case the last is kept (this trick handles Director and Producer variations nicely).
      See ignorable_keywords.

    This allows us to avoid bloat in the categorizations above.
    """
    role = role.split('(', maxsplit=1)[0].strip()  # Drop parentheticals
    # Drop meaningless words, unless this would remove all words in which case keep the last
    trimmed_role = " ".join(word for word in role.split() if word and word not in ignorable_keywords)
    return trimmed_role if trimmed_role else role.split()[-1]

# TODO: Create role_type() here and use it instead of the finagling in compare_staff. Will also let us do
#       fancier stuff like 'anything with "Animation" in it is animation type', without breaking our callers.
