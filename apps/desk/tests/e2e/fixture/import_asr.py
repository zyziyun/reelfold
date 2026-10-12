"""The transcriber of the import e2e (VSTUDIO_OUTPUT_TRANSCRIBER=<this file>:words): the finished video says this."""


def words(path, language=None):
    text = "the city lights from above. a night flight over the water."
    return [dict(w=w, t=round(0.3 + i * 0.4, 3), te=round(0.6 + i * 0.4, 3)) for i, w in enumerate(text.split())]
