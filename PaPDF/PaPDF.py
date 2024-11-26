import os, sys, io, zlib, math
from datetime import datetime
import collections
import struct

try:
    import TrueType
except Exception as e:
    from . import TrueType


class PaPDF:
    PAGE_FORMATS = {
        "A3": [297.0, 420.0],
        "A4": [210.0, 297.0],
        "A5": [148.5, 210.0],
        "LETTER": [215.9, 279.4],
        "LEGAL": [215.9, 355.6],
        "LINKEDIN_CAROUSEL_SQUARE": [91.44, 91.44], # 1080x1080 @300DPI
        "LINKEDIN_CAROUSEL_PORTRAIT": [91.44, 114.3], # 1080x1350 @300DPI
        "LINKEDIN_CAROUSEL_LANDSCAPE": [108.37, 60.96] # 1280x720 @300DPI
    }
    PROGRAM_NAME = "PaPDF v.1.1.9"
    PDF_VERSION = "1.4"
    MM_TO_DPI = 72 / 25.4
    def __init__(self, filename, pageFormat="A4", title=""):
        if sys.version_info < (3, 4):
            raise Exception("python3.4 is (at least) required")
        self.filename = filename
        self.title = title # PDF Metadata
        # Buffer that contains the actual PDF data:
        self.buffer = b""

        # Color variables:
        r=g=b=0
        self.stroke_color = "%.3f %.3f %.3f RG" % (r/255.0,g/255.0,b/255.0)
        self.fill_color = "%.3f %.3f %.3f rg" % (r/255.0,g/255.0,b/255.0)

        # Compress the text commands (can be turned off for debug purposes)
        self.compress = True

        try:
            self.w_mm, self.h_mm = PaPDF.PAGE_FORMATS[pageFormat.upper()]
        except:
            self.w_mm, self.h_mm = PaPDF.PAGE_FORMATS["A4"]

        # Handling of fonts: dict of fonts, current font name and font size,
        # with Helvetica being the default font.
        #
        # Each font contains a few (self-explainatory) fields. The field
        # named "fontObjectReference" will be populated when the font is
        # actually embedded in the PDF buffer. The "usedCharacters" variable
        # contains a (unique) set of characters that will be dispayed with this
        # very font. This is used later, for font glyph subsetting.
        self.fonts = {}
        self.fonts["Helvetica"] = {
            "fontId": 0,
            "fontType": "Embedded",
            "fileName": None,
            "fontObjectReference":-1,
            "usedCharacters": set(),
            "trueTypeParser": None,
        }
        self.currentFontName = "Helvetica"
        self.fontSize = 10
        self.lineThickness = 1

        # Page related variables: the page id, the pageStream.
        self.pageId = -1
        self.pageStream = b"" # bytes buffer

        # PDF specific object referncing system: objectCount is used as a
        # reference number, then the offsets are used at the footer of the PDF,
        # more specifically in the cross-reference table.
        self.objectCount = 2 # start at two, since the first object is /Pages
        # and the second object is the font reference table
        self.offsets = {}
        self.images = {}
        self.shadingObjects = []
        self.extGStateObjects = []


        self._bufferAppend("%PDF-"+self.PDF_VERSION)
        self.addPage()

    def setStrokeColor(self, color):
        color = color.lstrip("#")
        r,g,b = tuple(int(color[i:i+2], 16) for i in range(0,6,2))
        self.stroke_color = "%.3f %.3f %.3f RG" % (r/255.0,g/255.0,b/255.0)

    def setFillColor(self, color):
        color = color.lstrip("#")
        r,g,b = tuple(int(color[i:i+2], 16) for i in range(0,6,2))
        self.fill_color = "%.3f %.3f %.3f rg" % (r/255.0,g/255.0,b/255.0)

    def _bufferAppend(self, input, endLine="\n"):
        """
        Helper (private) function that adds the input to the private buffer.
        If the input or the endLine are a regular (unicode) str, they will
        automatically be converted into bytes. Passing another type as
        str or bytes, will trigger a string representation, then a bytes
        conversion .
        """
        if not isinstance(input, bytes) and not isinstance(input, str):
            input=str(input)
        if not isinstance(input, bytes):
            input = input.encode()
        if not isinstance(endLine, bytes):
            endLine = endLine.encode()
        self.buffer += (input + endLine)

    def _flushPageStream(self):
        """
        Helper (private) function to flush the page stream into the PDF buffer.
        """
        if len(self.pageStream)>0 :
            self._addNewObject()
            filter = ""
            content = self.pageStream
            if self.compress:
                filter = "/Filter /FlateDecode "
                content = zlib.compress(self.pageStream)
            self._bufferAppend("<<" + filter + "/Length " \
                + str(len(content)) + ">>")
            self._bufferAppend("stream")
            self._bufferAppend(content)
            self._bufferAppend("endstream")
            self._bufferAppend("endobj")

            self.pageStream = b""

    def addPage(self):
        """
        Add an empty page to the current PDF.
        """
        self._flushPageStream()
        self._addNewObject()
        self._bufferAppend("<</Type /Page")
        self._bufferAppend("/Parent 1 0 R")
        self._bufferAppend("/Resources 2 0 R")
        self._bufferAppend("/Group <</Type /Group /S /Transparency/CS "
            + "/DeviceRGB>>")
        self._bufferAppend("/Contents " + str(self.objectCount + 1) + " 0 R>>")
        self._bufferAppend("endobj")
        self.pageId += 1

    def __enter__(self):
        return self

    def __exit__(self,exc_type, exc_value, traceback):
        self.close()
        return isinstance(exc_value, TypeError)

    def addPar(self, x, y, lines):
        """
        Adds a sequence of lines (aka a paragraph), with a 135% font height
        text leading.
        """
        height = y
        for l in lines.split("\n"):
            self.addText(x, height, l)
            height -= self.fontSize * 1.35 / PaPDF.MM_TO_DPI

    def addText(self, x, y, multiLineText, maxLength=-1):
        """
        Add a single line text at positin (x,y). The coordinates system are in
        millimeters and the origin is the bottom left corner of the page.

        The optional argument `maxLength` sets the bounding maximum width, if
        the text exceeds this amount of mm, the rest of the text is split and
        displayed on a next line. The number of added text lines is returned by
        this function. Splits occur before the beginning of words (a word is a
        sequence of symbols - except the space char - " " char).
        """
        # Basic text escaping and converting to UTF-16BE (big-endian) encoding
        currFont = self.fonts[self.currentFontName]
        pdfFontId = currFont["fontId"] + 1 # PDF font indices start at 1

        # Update of the uniquely used characters, by the currFont font:
        newChars = [ord(c) for c in set(multiLineText) if ord(c) != 0]
        currFont["usedCharacters"] = currFont["usedCharacters"].union(newChars)


        output = ""
        output += "2 J" + "\n"
        output += "BT /F%d %.2f Tf ET\n" % (pdfFontId, self.fontSize)

        textSplits = []
        for text in multiLineText.split("\n"):
            text = text.strip()
            textLen = self.getTextWidth(text)
            if maxLength>0 and textLen>maxLength:
                currLine = None
                for word in text.split(" "):
                    if currLine is not None:
                        potCurrLine = "%s %s" % (currLine, word)
                    else:
                        potCurrLine = word
                    if self.getTextWidth(potCurrLine)>maxLength:
                        textSplits.append(currLine)
                        currLine = word
                    else:
                        currLine = potCurrLine
                if currLine is not None:
                    textSplits.append(currLine)
            else:
                textSplits.append(text)

        italicAngle = 0 # try 0.5
        currY = y
        for split in textSplits:
            split = split.encode("UTF-16BE").decode("Latin-1")\
                .replace("\\","\\\\").replace(")","\\)") \
                .replace("(","\\(").replace("\r","\\r")

            # TODO: support for italic text
            #output += "BT %s 1 0 %.2f 1 %.2f %.2f Tm (%s) Tj ET\n" \
            #    % (self.fill_color, italicAngle, \
            #        x * PaPDF.MM_TO_DPI, currY * PaPDF.MM_TO_DPI, \
            #        split)
            output += "BT %s %.2f %.2f Td (%s) Tj ET\n" \
                % (self.fill_color, \
                   x * PaPDF.MM_TO_DPI, currY * PaPDF.MM_TO_DPI, split)

            currY -= self.fontSize * 1.35 / PaPDF.MM_TO_DPI

        self.pageStream += output.encode("Latin-1")

        return len(textSplits)

    def _getHelveticaTextWidth(self, text, fullFontName):
        # Private function to compute the size (in mm) of an helvetica printed
        # text.
        # The helveticaOrdToWidth is a map of ord (char index) to width and it
        # was computed reading the Helvetica TTF font file, deducing the ord
        # with using the corresponding glyph, for each ord.

        if "bold" in fullFontName.lower():
            helveticaOrdToWidth = {61441: 0.61083984375, 8706: 0.494140625, 8710: 0.61181640625, 61442: 0.61083984375, 8719: 0.8232421875, 8721: 0.712890625, 8211: 0.55615234375, 8212: 1.0, 8725: 0.1669921875, 8216: 0.27783203125, 8217: 0.27783203125, 8218: 0.27783203125, 8220: 0.5, 8221: 0.5, 8222: 0.5, 32: 0.27783203125, 33: 0.3330078125, 34: 0.47412109375, 35: 0.55615234375, 36: 0.55615234375, 37: 0.88916015625, 38: 0.72216796875, 39: 0.23779296875, 40: 0.3330078125, 41: 0.3330078125, 42: 0.38916015625, 43: 0.583984375, 44: 0.27783203125, 45: 0.3330078125, 46: 0.27783203125, 47: 0.27783203125, 48: 0.55615234375, 49: 0.55615234375, 50: 0.55615234375, 51: 0.55615234375, 52: 0.55615234375, 53: 0.55615234375, 54: 0.55615234375, 55: 0.55615234375, 56: 0.55615234375, 57: 0.55615234375, 58: 0.3330078125, 59: 0.3330078125, 60: 0.583984375, 61: 0.583984375, 62: 0.583984375, 63: 0.61083984375, 64: 0.97509765625, 65: 0.72216796875, 66: 0.72216796875, 67: 0.72216796875, 68: 0.72216796875, 69: 0.6669921875, 70: 0.61083984375, 71: 0.77783203125, 72: 0.72216796875, 73: 0.27783203125, 74: 0.55615234375, 75: 0.72216796875, 76: 0.61083984375, 77: 0.8330078125, 78: 0.72216796875, 79: 0.77783203125, 80: 0.6669921875, 81: 0.77783203125, 82: 0.72216796875, 83: 0.6669921875, 84: 0.61083984375, 85: 0.72216796875, 86: 0.6669921875, 87: 0.94384765625, 88: 0.6669921875, 89: 0.6669921875, 90: 0.61083984375, 91: 0.3330078125, 92: 0.27783203125, 93: 0.3330078125, 94: 0.583984375, 95: 0.55615234375, 96: 0.3330078125, 97: 0.55615234375, 98: 0.61083984375, 99: 0.55615234375, 100: 0.61083984375, 101: 0.55615234375, 102: 0.3330078125, 103: 0.61083984375, 104: 0.61083984375, 105: 0.27783203125, 106: 0.27783203125, 107: 0.55615234375, 108: 0.27783203125, 109: 0.88916015625, 110: 0.61083984375, 111: 0.61083984375, 112: 0.61083984375, 113: 0.61083984375, 114: 0.38916015625, 115: 0.55615234375, 116: 0.3330078125, 117: 0.61083984375, 118: 0.55615234375, 119: 0.77783203125, 120: 0.55615234375, 121: 0.55615234375, 122: 0.5, 123: 0.38916015625, 124: 0.27978515625, 125: 0.38916015625, 126: 0.583984375, 8729: 0.27783203125, 8730: 0.548828125, 160: 0.27783203125, 161: 0.3330078125, 162: 0.55615234375, 163: 0.55615234375, 164: 0.55615234375, 165: 0.55615234375, 167: 0.55615234375, 168: 0.3330078125, 169: 0.73681640625, 170: 0.3701171875, 171: 0.55615234375, 172: 0.583984375, 173: 0.3330078125,174: 0.73681640625, 176: 0.39990234375, 177: 0.548828125, 180: 0.3330078125, 8734: 0.712890625, 182: 0.55615234375, 183: 0.27783203125, 184:0.3330078125, 186: 0.365234375, 187: 0.55615234375, 191: 0.61083984375, 192: 0.72216796875, 193: 0.72216796875, 194: 0.72216796875, 195: 0.72216796875, 196: 0.72216796875, 197: 0.72216796875, 198: 1.0, 8225: 0.55615234375, 200: 0.6669921875, 201: 0.6669921875, 202: 0.6669921875, 203: 0.6669921875, 204: 0.27783203125, 205: 0.27783203125, 206: 0.27783203125, 207: 0.27783203125, 209: 0.72216796875, 210: 0.77783203125,211: 0.77783203125, 212: 0.77783203125, 213: 0.77783203125, 214: 0.77783203125, 216: 0.77783203125, 217: 0.72216796875, 218: 0.72216796875,219: 0.72216796875, 220: 0.72216796875, 733: 0.3330078125, 223: 0.61083984375, 224: 0.55615234375, 225: 0.55615234375, 226: 0.55615234375, 227: 0.55615234375, 228: 0.55615234375, 229: 0.55615234375, 230: 0.88916015625, 231: 0.55615234375, 232: 0.55615234375, 233: 0.55615234375, 234: 0.55615234375, 235: 0.55615234375, 236: 0.27783203125, 237: 0.27783203125, 238: 0.27783203125, 239: 0.27783203125, 241: 0.61083984375, 242: 0.61083984375, 243: 0.61083984375, 244: 0.61083984375, 245: 0.61083984375, 246: 0.61083984375, 247: 0.548828125, 248: 0.61083984375, 249: 0.61083984375, 250: 0.61083984375, 251: 0.61083984375, 252: 0.61083984375, 255: 0.55615234375, 64257: 0.61083984375, 64258: 0.61083984375, 8226: 0.35009765625, 728: 0.3330078125, 729: 0.3330078125, 730: 0.3330078125, 8240: 1.0, 8482: 1.0, 731: 0.3330078125, 8486: 0.76806640625, 732: 0.3330078125, 305: 0.27783203125, 181: 0.576171875, 710: 0.3330078125, 338: 1.0, 339: 0.94384765625, 8249: 0.3330078125, 8250: 0.3330078125, 199: 0.72216796875, 61446: 0.548828125, 8747: 0.27392578125, 711: 0.3330078125, 376: 0.6669921875, 8230: 1.0, 894: 0.3330078125, 8805: 0.548828125, 402: 0.55615234375, 916: 0.61181640625, 8260: 0.1669921875, 937: 0.76806640625, 713: 0.3330078125, 8776: 0.548828125, 960: 0.548828125, 8800: 0.548828125, 9674: 0.494140625, 8804: 0.548828125, 8224: 0.55615234375}
        elif "italic" in fullFontName.lower():
            # Unfortunately these are the widths of a slightly different font
            # variant than the official helvetica regular italic font:
            # HelveticaNeueCyr is used here as the best approximation.
            helveticaOrdToWidth = {57344: 0.389, 1025: 0.611, 1026: 0.746, 1027: 0.547, 1028: 0.722, 1029: 0.648, 1030: 0.259, 1031: 0.259, 1032: 0.519, 1033: 1.0, 1034: 1.0, 1035: 0.746, 1036: 0.667, 1038: 0.611, 1039: 0.722, 1040: 0.667, 1041: 0.685, 1042: 0.685, 1043: 0.547, 1044: 0.722, 1045: 0.611, 1046: 1.0, 1047: 0.648, 1048: 0.722, 1049: 0.722, 1050: 0.667, 1051: 0.685, 1052: 0.87, 1053: 0.722, 1054: 0.759, 1055: 0.722, 32: 0.278, 33: 0.259, 34: 0.426, 35: 0.556, 36: 0.556, 37: 0.926, 38: 0.63, 39: 0.278, 40: 0.259, 41: 0.259, 42: 0.352, 43: 0.6, 44: 0.278, 45: 0.389, 46: 0.278, 47: 0.333, 48: 0.556, 49: 0.556, 50: 0.556, 51: 0.556, 52: 0.556, 53: 0.556, 54: 0.556, 55: 0.556, 56: 0.556, 57: 0.556, 58: 0.278, 59: 0.278, 60: 0.6, 61: 0.6, 62: 0.6, 63: 0.556, 64: 0.8, 65: 0.667, 66: 0.685, 67: 0.722, 68: 0.704, 69: 0.611, 70: 0.574, 71: 0.759, 72: 0.722, 73: 0.259, 74: 0.519, 75: 0.667, 76: 0.556, 77: 0.87, 78: 0.722, 79: 0.759, 80: 0.648, 81: 0.759, 82: 0.685, 83: 0.648, 84: 0.574, 85: 0.722, 86: 0.611, 87: 0.926, 88: 0.611, 89: 0.611, 90: 0.611, 91: 0.259, 92: 0.333, 93: 0.259, 94: 0.6, 95: 0.5, 96: 0.222, 97: 0.519, 98: 0.593, 99: 0.537, 100: 0.593, 101: 0.537, 102: 0.296, 103: 0.574, 104: 0.556, 105: 0.222, 106: 0.222, 107: 0.481, 108: 0.222, 109: 0.852, 110: 0.556, 111: 0.574, 112: 0.593, 113: 0.593, 114: 0.333, 115: 0.481, 116: 0.315, 117: 0.556, 118: 0.481, 119: 0.759, 120: 0.481, 121: 0.481, 122: 0.444, 123: 0.333, 124: 0.222, 125: 0.333, 126: 0.6, 1057: 0.722, 8222: 0.426, 1168: 0.547, 1169: 0.42, 1113: 0.778, 8217: 0.278, 8218: 0.278, 163: 0.556, 164: 0.556, 166: 0.222, 167: 0.556, 169: 0.8, 171: 0.463, 172: 0.6, 174: 0.4, 8221: 0.426, 176: 0.4, 177: 0.6, 8730: 0.6, 1114: 0.778, 8734: 0.741, 182: 0.6, 183: 0.278, 187: 0.463, 1056: 0.648, 8225: 0.556, 1058: 0.574, 1112: 0.222, 8804: 0.6, 1115: 0.556, 1059: 0.611, 1060: 0.778, 1061: 0.611, 1062: 0.722, 1063: 0.667, 8805: 0.6, 1116: 0.5, 1064: 1.073, 1065: 1.083, 1066: 0.803, 1067: 0.871, 1068: 0.648, 1069: 0.722, 1070: 1.0, 8470: 1.0, 8226: 0.5, 1071: 0.667, 1072: 0.519, 8482: 0.99, 57345: 0.278, 1073: 0.574, 1118: 0.481, 1074: 0.537, 1110: 0.222, 1075: 0.42, 1076: 0.574, 1077: 0.537, 8211: 0.5, 181: 0.556, 1078: 0.778, 1119: 0.556, 1079: 0.5, 8240: 1.074, 1080: 0.556, 1081: 0.556, 1082: 0.5, 8212: 1.0, 1083: 0.556, 1084: 0.685, 1085: 0.556, 1086: 0.574, 8230: 1.0, 1088: 0.593, 1089: 0.537, 8776: 0.6, 1087: 0.556, 1090: 0.463, 8220: 0.426, 402: 0.556, 1091: 0.481, 1092: 0.8, 1093: 0.481, 1094: 0.57, 1095: 0.527, 1096: 0.809, 8249: 0.259, 1097: 0.824, 1098: 0.611, 1099: 0.704, 1111: 0.222, 8800: 0.6, 1100: 0.519, 8710: 0.67, 247: 0.6, 1101: 0.537, 8250: 0.259, 1102: 0.766, 8216: 0.278, 1103: 0.537, 1105: 0.537, 8224: 0.556, 1106: 0.556, 1107: 0.42, 1108: 0.537, 1109: 0.481}
        else:
            helveticaOrdToWidth = {0: 0.0, 8: 0.0, 9: 0.27783203125, 10: 0.27783203125, 13: 0.27783203125, 29: 0.0, 32: 0.27783203125, 33: 0.27783203125,34: 0.35498046875, 35: 0.55615234375, 36: 0.55615234375, 37: 0.88916015625, 38: 0.6669921875, 39: 0.19091796875, 40: 0.3330078125, 41: 0.3330078125, 42: 0.38916015625, 43: 0.583984375, 44: 0.27783203125, 45: 0.3330078125, 46: 0.27783203125, 47: 0.27783203125, 48: 0.55615234375, 49: 0.55615234375, 50: 0.55615234375, 51: 0.55615234375, 52: 0.55615234375, 53: 0.55615234375, 54: 0.55615234375, 55: 0.55615234375, 56: 0.55615234375, 57: 0.55615234375, 58: 0.27783203125, 59: 0.27783203125, 60: 0.583984375, 61: 0.583984375, 62: 0.583984375, 63: 0.55615234375, 64: 1.01513671875, 65: 0.6669921875, 66: 0.6669921875, 67: 0.72216796875, 68: 0.72216796875, 69: 0.6669921875, 70: 0.61083984375, 71: 0.77783203125, 72: 0.72216796875, 73: 0.27783203125, 74: 0.5, 75: 0.6669921875, 76: 0.55615234375, 77: 0.8330078125, 78: 0.72216796875, 79: 0.77783203125, 80: 0.6669921875, 81: 0.77783203125, 82: 0.72216796875, 83: 0.6669921875, 84: 0.61083984375, 85: 0.72216796875, 86: 0.6669921875, 87: 0.94384765625, 88: 0.6669921875, 89: 0.6669921875, 90: 0.61083984375, 91: 0.27783203125, 92: 0.27783203125, 93: 0.27783203125, 94: 0.46923828125, 95: 0.55615234375, 96: 0.3330078125, 97: 0.55615234375, 98: 0.55615234375, 99: 0.5, 100: 0.55615234375, 101: 0.55615234375, 102: 0.27783203125, 103: 0.55615234375, 104: 0.55615234375, 105: 0.22216796875, 106: 0.22216796875, 107: 0.5, 108: 0.22216796875, 109: 0.8330078125, 110: 0.55615234375,111: 0.55615234375, 112: 0.55615234375, 113: 0.55615234375, 114: 0.3330078125, 115: 0.5, 116: 0.27783203125, 117: 0.55615234375, 118: 0.5, 119: 0.72216796875, 120: 0.5, 121: 0.5, 122: 0.5, 123: 0.333984375, 124: 0.259765625, 125: 0.333984375, 126: 0.583984375, 160: 0.27783203125, 161: 0.3330078125, 162: 0.55615234375, 163: 0.55615234375, 164: 0.55615234375, 165: 0.55615234375, 166: 0.259765625, 167: 0.55615234375, 168: 0.3330078125, 169: 0.73681640625, 170: 0.3701171875, 171: 0.55615234375, 172: 0.583984375, 173: 0.3330078125, 174: 0.73681640625, 175: 0.3330078125, 176: 0.39990234375, 177: 0.548828125, 178: 0.3330078125, 179: 0.3330078125, 180: 0.3330078125, 181: 0.576171875, 182: 0.537109375, 183: 0.27783203125, 184: 0.3330078125, 185: 0.3330078125, 186: 0.365234375, 187: 0.55615234375, 188: 0.833984375, 189: 0.833984375, 190: 0.833984375, 191: 0.61083984375, 192: 0.6669921875, 193: 0.6669921875, 194: 0.6669921875, 195: 0.6669921875, 196: 0.6669921875, 197: 0.6669921875, 198: 1.0, 199: 0.72216796875, 200: 0.6669921875, 201: 0.6669921875, 202: 0.6669921875, 203: 0.6669921875, 204: 0.27783203125, 205: 0.27783203125, 206: 0.27783203125, 207: 0.27783203125, 208: 0.72216796875, 209: 0.72216796875, 210: 0.77783203125, 211: 0.77783203125, 212: 0.77783203125, 213:0.77783203125, 214: 0.77783203125, 215: 0.583984375, 216: 0.77783203125, 217: 0.72216796875, 218: 0.72216796875, 219: 0.72216796875, 220: 0.72216796875, 221: 0.6669921875, 222: 0.6669921875, 223: 0.61083984375, 224: 0.55615234375, 225: 0.55615234375, 226: 0.55615234375, 227: 0.55615234375, 228: 0.55615234375, 229: 0.55615234375, 230: 0.88916015625, 231: 0.5, 232: 0.55615234375, 233: 0.55615234375, 234: 0.55615234375, 235:0.55615234375, 236: 0.27783203125, 237: 0.27783203125, 238: 0.27783203125, 239: 0.27783203125, 240: 0.55615234375, 241: 0.55615234375, 242: 0.55615234375, 243: 0.55615234375, 244: 0.55615234375, 245: 0.55615234375, 246: 0.55615234375, 247: 0.548828125, 248: 0.61083984375, 249: 0.55615234375, 250: 0.55615234375, 251: 0.55615234375, 252: 0.55615234375, 253: 0.5, 254: 0.55615234375, 255: 0.5}
        sum = 0
        for letter in text[:]:
            o = ord(letter)
            if not o in helveticaOrdToWidth:
                print("Warning: not found letter =", letter)
            else:
                sum += helveticaOrdToWidth[o]
        return sum  * self.fontSize / 72.0 * 25.4
        # The previous approach is more robust in case of an unknown character.
        # return sum([helveticaOrdToWidth[ord(x)] for x in text[:]]) \
        #    * self.fontSize / 72.0 * 25.4

    def getTextWidth(self, text):
        """
        Returns the text width (in mm) given the current font settings.
        """
        if self.currentFontName.startswith("Helvetica"):
            return self._getHelveticaTextWidth(text, self.currentFontName)

        if self.fonts[self.currentFontName]["trueTypeParser"] is None:
            # Caching the TrueTypeParser object for future use.
            self.fonts[self.currentFontName]["trueTypeParser"] = \
                TrueType.TrueTypeParser(self.fonts[self.currentFontName] \
                ["fileName"])
        ttp = self.fonts[self.currentFontName]["trueTypeParser"]
        return ttp.getTextWidth(text, self.fontSize)

    def addLine(self, x0, y0, x1, y1):
        """
        Add a line from (x0,y0) to (x1,y1)
        """
        output = ""
        output += "%.2f w\n %s\n 0 J\n" % (self.lineThickness * PaPDF.MM_TO_DPI, self.stroke_color)
        output += "%.2f %.2f m %.2f %.2f l S\n" \
            % (x0 * PaPDF.MM_TO_DPI,
            y0 * PaPDF.MM_TO_DPI,
            x1 * PaPDF.MM_TO_DPI,
            y1 * PaPDF.MM_TO_DPI)
        self.pageStream += output.encode("Latin-1")

    def addPath(self, points, fill=False, close=True):
        """
        Given a list of points (a list of (x,y) millimeters coordinates tuples),
        this function draws a path on the current page.
        If (strictly) less than 2 points are given, nothing is done.
        """
        if len(points)<2:
            return
        points = [(x* PaPDF.MM_TO_DPI, y * PaPDF.MM_TO_DPI) for (x,y) in points]
        output = "%d %d m\n" % points.pop(0)
        for p in points:
            output += "%d %d l\n" % p

        output += "%d w\n" % self.lineThickness

        output += "%s\n" % self.stroke_color
        output += "%s\n" % self.fill_color

        if fill:
            output += "f "
        if close:
            output += "s" # s = h S : close and stroke
        else:
            output += "S" # only stroke
        output +="\n"
        self.pageStream += output.encode("Latin-1")

    def _decodeJPG(self, fileObject):
        # Helper function to parse a JPG fileobject and raise in case bad format
        # Source: https://www.disktuna.com/list-of-jpeg-markers/
        h, w, stream, extraInfos, extraObjects = 0, 0, b'', [], []
        # Reading the JPEG stream:
        hasFoundSize = False
        while not hasFoundSize:
            b0, b1 = struct.unpack('>BB', fileObject.read(2))
            if b0 != 0xFF:
                raise Exception("Wrong JPEG marker prefix")
            if ((b1 >= 0xD0 and b1 <= 0xD9) or # Restart Markers
                (b1 == 0xC8 or b1 >= 0xF0 and b1 <= 0xFD)): # JPEG extensions
                continue # simple marker with no following bytes
            else:
                length = struct.unpack('>H', fileObject.read(2))[0]
                if length <= 2:
                    raise Error("Invalid length after a Start of Frame marker.")
                data = fileObject.read(length - 2)
                # The start of frame consists of 4 ranges of markers:
                if (b1 >= 0xC0 and b1 <= 0xC3) or \
                    (b1 >= 0xC5 and b1 <= 0xC7) or \
                    (b1 >= 0xC9 and b1 <= 0xCB) or \
                    (b1 >= 0xCD and b1 <= 0xCF):
                    # If a marker falls into one of the previous marker ranges,
                    # then it contains interesting data.
                    bitsPerChannel, h, w, layersQuantity_ = \
                        struct.unpack_from('>BHHB', data)
                    extraInfos = [
                        "/ColorSpace /DeviceRGB",
                        "/BitsPerComponent %d" % bitsPerChannel,
                        "/Filter /DCTDecode",
                    ]
                    hasFoundSize = True
        if not hasFoundSize:
            raise Exception("Could not read JPEG payload data")
        fileObject.seek(0)
        return h, w, fileObject.read(), extraInfos, extraObjects

    def _decodePNG(self, fileObject):
        # Helper function to parse a PNG fileobject and raise in case bad format
        h, w, stream, extraInfos, extraObjects = 0, 0, b'', [], []

        # Parsing the file header
        # (ref: http://www.libpng.org/pub/png/book/chapter08.html)
        header = fileObject.read(8)
        if header != bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]):
            raise Exception("Could not parse the PNG header")

        def read4ByteNum(fileObject, numBytes=4, unsigned=True):
            # Helper function to read a `numBytes`-byte number on the PNG stream
            data = fileObject.read(numBytes)
            output = 0
            for i in range(0, numBytes):
                output += (data[i] << (8*(numBytes-1-i)))
            if not unsigned and (output & (1 << 8*numBytes-1)):
                # Reversing the two's complement:
                output -= (1 << 8*numBytes)
            return output

        # parsing the the IHDR chunk:
        # The IHDR chunk must appear FIRST. It contains:
        # (ref: http://www.libpng.org/pub/png/spec/1.2/PNG-Chunks.html)
        length = read4ByteNum(fileObject)
        chunkType = fileObject.read(4).decode()
        if chunkType != "IHDR":
            raise Exception("Could not parse the PNG IHDR chunk")
        width = read4ByteNum(fileObject)
        height = read4ByteNum(fileObject)
        bitDepth = read4ByteNum(fileObject,1)
        colorType = read4ByteNum(fileObject,1)
        compressionMethod = read4ByteNum(fileObject,1)
        filterMethod = read4ByteNum(fileObject,1)
        interalaceMethod = read4ByteNum(fileObject,1)
        crc = fileObject.read(4)

        if colorType == 2 or colorType == 6:
            colorSpace ='DeviceRGB'
            # RGB color type:
            channels = 3
        elif ct == 0 or ct == 4:
            colorSpace ='DeviceGray'
            channels = 1
        else:
            colorSpace ='Indexed'
            channels = 1

        decodeParms = "/Predictor 15 /Colors %d" % channels \
            + " /BitsPerComponent %d /Columns %d" % (bitDepth, width)

        # fetching and parsing the other chunks:
        plteDATA = b""
        trnsDATA = b""
        streamDATA = b""
        length = 1
        while length>0:
            length = read4ByteNum(fileObject)
            chunkType = fileObject.read(4).decode()
            if chunkType == "PLTE":
                plteDATA += fileObject.read(length)
            elif chunkType == "tRNS":
                # Handling of PNG transparency:
                trnsDATA = bytearray(fileObject.read(length))
                if colorType == 0:
                    trnsDATA = [trnsDATA[1]]
                elif colorType == 2:
                    trnsDATA = [trnsDATA[1], trnsDATA[3], trnsDATA[5]]
                else:
                    offset = -1
                    for i,b in enumerate(trnsDATA):
                        if b == 0x00:
                            offset = i
                    if offset > 0:
                        trnsDATA = [offset]
                    else:
                        trnsDATA = []
                trnsDATA = bytes(trnsDATA)
            elif chunkType == "IDAT":
                streamDATA += fileObject.read(length)
            elif chunkType == "IEND":
                break
            else:
                fileObject.seek(length, os.SEEK_CUR) # skipping data
            # each chunk is terminated by a CRC:
            crc = fileObject.read(4)

        colorStream = bytearray()
        smaskStream = bytearray()

        dec = zlib.decompress(streamDATA)

        if colorType == 4: # Grayscale-Alpha image
            offsetInScanline = 0
            for b in dec:
                if offsetInScanline%(width*2+1) == 0:
                    # scanline filter type header, apending it to both streams
                    colorStream.append(b)
                    smaskStream.append(b)
                    offsetInScanline = 0
                else:
                    if (offsetInScanline-1)%2<1: # -1 because of scanline header
                        colorStream.append(b)
                    else:
                        smaskStream.append(b)
                offsetInScanline += 1
        elif colorType == 6: # RGBA image
            offsetInScanline = 0
            for b in dec:
                if offsetInScanline%(width*4+1) == 0:
                    # scanline filter type header, apending it to both streams
                    colorStream.append(b)
                    smaskStream.append(b)
                    offsetInScanline = 0
                else:
                    if (offsetInScanline-1)%4<3: # -1 because of scanline header
                        colorStream.append(b)
                    else:
                        smaskStream.append(b)
                offsetInScanline += 1
        else:
            raise Exception("Unsupported PNG color type, " \
               + "please use a RGBA color type or Greyscale/Alpha color type.")

        colorStream = zlib.compress(colorStream)
        smaskStream = zlib.compress(smaskStream)

        smaskDecodeParms = "/Predictor 15 /Colors %d" % 1 \
            + " /BitsPerComponent %d /Columns %d" % (bitDepth, width)
        # for the transparency mask, only 1 channel is used.

        extraInfos = [
            "/ColorSpace /%s" % colorSpace,
            "/BitsPerComponent %d" % bitDepth,
            "/Filter /FlateDecode",
            "/DecodeParms <<%s>>" % decodeParms,
            # TODO: refactor smask and palette and others...
        ]
        extraObjects = {
            "SMask": {
                "Keys":[
                        "/Type /XObject",
                        "/Subtype /Image",
                        "/Width %d" % width,
                        "/Height %d" % height,
                        "/ColorSpace /DeviceGray",
                        "/BitsPerComponent %d" % bitDepth,
                        "/Filter /FlateDecode",
                        "/DecodeParms <<%s>>" % smaskDecodeParms,
                        "/Length %d" % len(smaskStream),
                    ],
                "Stream": smaskStream
                }

        }
        return height, width, colorStream, extraInfos, extraObjects


    def addImage(self, filename, x, y, width, height):
        with open(filename,"rb") as f:
            h, w, stream, extraInfos, extraObjects = 0, 0, b'', [], []
            imageId = len(self.images)+1 # PDF object refs starts at 1
            hasBeenEmbedded = False

            imgExt = os.path.splitext(filename)[1].lower().replace(".","")
            if imgExt == "jpeg" or imgExt == "jpg":
                try:
                    h, w, stream, extraInfos, extraObjects = self._decodeJPG(f)
                    hasBeenEmbedded = True
                except Exception as e:
                    pass
            elif imgExt == "png":
                try:
                    h, w, stream, extraInfos, extraObjects = self._decodePNG(f)
                    hasBeenEmbedded = True
                except Exception as e:
                    pass

            if not hasBeenEmbedded:
                # Iterative try to parse the image:
                for func in [self._decodeJPG, self._decodePNG]:
                    try:
                        f.seek(0)
                        h, w, stream, extraInfos, extraObjects = func(f)
                        hasBeenEmbedded = True
                        break
                    except Exception as e:
                        pass
            if not hasBeenEmbedded:
                raise Exception("The provided image could not be read.")
            else:
                self.images[filename] = {
                    "height": h,
                    "width": w,
                    "fontObjectReference": -1,
                    "imageId": imageId,
                    "data": stream,
                    "extraInfos": extraInfos,
                    "extraObjects": extraObjects,
                }
        output = ""
        output += "q %.2f 0 0 %.2f %.2f %.2f cm /I%d Do Q\n" \
        % (width * PaPDF.MM_TO_DPI,
            height * PaPDF.MM_TO_DPI,
            x * PaPDF.MM_TO_DPI,
            y * PaPDF.MM_TO_DPI,
            imageId)
        self.pageStream += output.encode("Latin-1")

    def setLineThickness(self, thickness):
        """ Set the line thickness (in millimeters)"""
        self.lineThickness = thickness

    def getLineThickness(self):
        """ get the line thickness (in millimeters)"""
        return self.lineThickness

    def addEAN13(self, x0, y0, numbers, validateChecksum=True):
        if len(numbers) != 13:
            raise Exception("The EAN barcode expects a sequence of 9 numbers")

        # validating of the checksum
        # (the last digit is a weighted sum of the 12 previous digits):
        receivedChecksum = int(numbers[12])
        computedChecksum = 0
        weights = [1,3]*6
        computedChecksum = sum([int(d) * w for d,w in zip(numbers[0:12], weights)])
        computedChecksum = (10-(computedChecksum%10))%10

        numbers = numbers[0:12] + str(computedChecksum)

        if validateChecksum and not computedChecksum == receivedChecksum:
            raise Exception("The EAN barcode checksum (last digit) is " \
                + "incorred (got %d, should be %d)" \
                % (receivedChecksum, computedChecksum))


        patterns = ["LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG", "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL"]
        lValues = [0x0D, 0x19, 0x13, 0x3D, 0x23, 0x31, 0x2F, 0x3B, 0x37, 0x0B]

        # Measurements in millimeters:
        longBarHeight = 22.85
        barWidth = 0.33
        smallBarsBottomVSpace = 1.5
        textBottomVSpace = 2.33
        leftMargin =  1.6

        oldLineThickness = self.lineThickness
        self.lineThickness = barWidth

        # start marker (101):
        x = x0 + leftMargin + barWidth / 2.0 # border-to-center offset
        y = y0 + textBottomVSpace
        h = longBarHeight
        for i in range(3):
            if i%2 == 0:
                self.addLine(x, y, x, y + h)
            x += barWidth

        # left first half:
        pattern = patterns[int(numbers[0])]
        h = longBarHeight - smallBarsBottomVSpace
        y = y0 + textBottomVSpace + smallBarsBottomVSpace

        # the first char is encoded by choosing a pattern, Skipping it below:
        for i, n in enumerate(numbers[1:7]):
            try:
                d = int(n)
                bitValue = lValues[d]
                table = pattern[i]
                rng = list(range(0,7))
                if table == "G":
                    rng.reverse()
                    bitValue ^= 0x7F
                for j in rng:
                    if ((bitValue >> (6-j) ) & 0x01)  == 1:
                        self.addLine(x, y, x, y + h)
                    x += barWidth
            except Exception as e:
                raise Exception("Each of the 13 digits must be in [0-9].")

        # middle marker (01010):
        y = y0 + textBottomVSpace
        h = longBarHeight
        for i in range(5):
            if i%2 == 1:
                self.addLine(x, y, x, y + h)
            x += barWidth

        h = longBarHeight - smallBarsBottomVSpace
        y = y0 + textBottomVSpace + smallBarsBottomVSpace
        # right second half:
        for i, n in enumerate(numbers[7:13]):
            d = int(n)
            value = lValues[d] ^ 0x7F
            for j in range(0,7):
                if ((value >> (6-j) ) & 0x01)  == 1:
                    self.addLine(x, y, x, y + h)
                x += barWidth


        # end marker (01010):
        y = y0 + textBottomVSpace
        h = longBarHeight
        for i in range(3):
            if i%2 == 0:
                self.addLine(x, y, x, y + h)
            x += barWidth

        # Bottom text:
        oldFontSize = self.fontSize
        self.fontSize = 8
        self.addText(x0, y0, numbers[0])
        x = x0 + leftMargin + 1 + 3 * barWidth
        y = y0
        for i,n in enumerate(numbers[1:]):
            self.addText(x, y, n)
            x += 7 * barWidth
            if i == 5:
                x += 2 * barWidth
        x += 1
        self.addText(x, y0, ">")

        # Restoring the original values:
        self.fontSize = oldFontSize
        self.lineThickness = oldLineThickness

    def _addNewObject(self):
        """
        Helper (private) function to add a new object on the PDF buffer and
        update the reference numbers.
        """
        self.objectCount += 1
        self.offsets[self.objectCount] = len(self.buffer)
        self._bufferAppend(str(self.objectCount)+" 0 obj")

    def _out_prefix_paren(self, prefix, input):
        input = input.replace("\\","\\\\").replace(")","\\)") \
            .replace("(","\\(").replace("\r","\\r")
        self._bufferAppend("/%s (%s)" % (prefix, input))

    def addTrueTypeFont(self, fontName, fileName):
        """
        Add a TrueType font to the PDF. Only necessary glyphs will be embedded
        in the document (font subsetting).
        """
        if len(self.fonts.items()) >= 625:
            # Simple and realistic limitation: with the current implementation
            # the font prefix can only hold 625 fonts (25 possibilities over
            # the two last characters in the prefix). A better solution might
            # exist but 625 fonts seems a decent font embedding upper bound.
            raise Exception("Warning: cannot add more than 625 TrueType fonts.")

        fontId = len(self.fonts.items())
        fontObjectReference = -1 # For now, no reference is available. it will
        # be created later, in the _addTrueTypeFonts() function.
        self.fonts[fontName] = {
            "fontId": fontId,
            "fontType": "TrueType",
            "fileName": fileName,
            "fontObjectReference": fontObjectReference,
            "usedCharacters": set(range(1,32)),
            "trueTypeParser": None,
        }
    def setFont(self, fontName, fontSize=-1):

        # Helvetica variants are only added to the pdf upon usage:
        if fontName.lower() in ["helvetica-bold", "helvetica-italic"]:
            if not fontName in self.fonts:
                self.fonts[fontName] = {
                    "fontId":  len(self.fonts.items()),
                    "fontType": "Embedded",
                    "fileName": None,
                    "fontObjectReference":-1,
                    "usedCharacters": set(),
                    "trueTypeParser": None,
                }
        self.currentFontName = fontName
        if fontSize >=0 :
            self.fontSize = fontSize

    def setFontSize(self, fontSize=-1):
        self.fontSize = fontSize

    def createExtGStateObject(self, strokeAlpha, fillAlpha, blendMode):
        extGStateObjectId = len(self.extGStateObjects) + 1 # Starting id at 1
        extGStateObjectReference = -1 # Created later
        self.extGStateObjects.append({
            "strokeAlpha": strokeAlpha,
            "fillAlpha": strokeAlpha,
            "blendMode": blendMode,
            "extGStateObjectId": extGStateObjectId,
            "extGStateObjectReference": extGStateObjectReference
        })
        return extGStateObjectId
    def createGradient(self, start2Coords, startColorHex, end2Coords, \
        endColorHex):

        def hex_to_color_array(hex_color):
            hex_color = hex_color.lstrip('#')
            if len(hex_color) != 6:
                raise ValueError("HEX color must be in the format '#RRGGBB'")
            r = int(hex_color[0:2], 16) / 255.0
            g = int(hex_color[2:4], 16) / 255.0
            b = int(hex_color[4:6], 16) / 255.0
            return [r, g, b]

        shadingObjectId = len(self.shadingObjects) + 1 # Starting id at 1
        shadingObjectReference = -1 # Created later
        print( [*start2Coords, *end2Coords])
        self.shadingObjects.append({
            "coords": [*start2Coords, *end2Coords],
            "startColor": hex_to_color_array(startColorHex),
            "endColor": hex_to_color_array(endColorHex),
            "shadingObjectId": shadingObjectId,
            "shadingObjectReference": shadingObjectReference
        })
        return shadingObjectId

    def _addShadingObjects(self):
        for shadingObject in self.shadingObjects:
            self._addNewObject()
            shadingObject["shadingObjectReference"] = self.objectCount

            self._bufferAppend("<<")
            self._bufferAppend("/ShadingType 2")
            self._bufferAppend("/ColorSpace /DeviceRGB")
            self._bufferAppend("/Coords [%s]" % \
                (" ".join([str(x) for x in shadingObject["coords"]])))

            self._bufferAppend("/Function")
            self._bufferAppend("<<")
            self._bufferAppend("/FunctionType 2")
            self._bufferAppend("/Domain [0 1]")
            self._bufferAppend("/C0 [%s]" % \
                (" ".join([str(x) for x in shadingObject["startColor"]])))
            self._bufferAppend("/C1 [%s]" % \
                (" ".join([str(x) for x in shadingObject["endColor"]])))
            self._bufferAppend("/N 1")
            self._bufferAppend(">>")

            self._bufferAppend("/Extend [true true]")
            self._bufferAppend(">>")
            self._bufferAppend("endobj")

    def _addExtGStateObjects(self):
        for extGStateObject in self.extGStateObjects:
            self._addNewObject()
            extGStateObject["extGStateObjectReference"] = self.objectCount

            self._bufferAppend("<< /Type /ExtGState")
            self._bufferAppend("/CA %f" % extGStateObject["strokeAlpha"])
            self._bufferAppend("/ca %f" % extGStateObject["fillAlpha"])
            self._bufferAppend("/BM /%s" % extGStateObject["blendMode"])
            self._bufferAppend(">>")

            self._bufferAppend("endobj")

    def addGradientText(self, gradientId, coordinates, text, extGStateObjectId=None):
        currFont = self.fonts[self.currentFontName]
        fontId = currFont["fontId"] + 1 # PDF font indices start at 1

        # Update of the uniquely used characters, by the currFont font:
        newChars = [ord(c) for c in set(text) if ord(c) != 0]
        currFont["usedCharacters"] = currFont["usedCharacters"].union(newChars)


        output = ""
        output += "q" + "\n"
        output += "BT" + "\n"
        output += "/F%d %.2f Tf\n" % (fontId, self.fontSize)
        output += "%s Td " % " ".join([str(x) for x in coordinates])+ "\n"
        output += "7 Tr" + "\n"
        #output += "1 0 0 1 10 10 Tm " + "\n"
        output += "(%s) Tj" % text + "\n"
        output += "ET" + "\n"
        if extGStateObjectId is not None:
            output += "/GS"+str(extGStateObjectId)+" gs" + "\n"
        output += "/Sh"+str(gradientId)+" sh" + "\n"
        output += "Q" + "\n"

        self.pageStream += output.encode("Latin-1")

    def _addImageStreams(self):
        filter = ""
        if self.compress:
            filter = "/Filter /FlateDecode "

        for imageFilename, imgDesc in self.images.items():
            self.images[imageFilename]["fontObjectReference"] = \
                self.objectCount + 1

            self._addNewObject()
            self._bufferAppend("<</Type /XObject")
            self._bufferAppend("/Subtype /Image")
            self._bufferAppend("/Width %d" % imgDesc["width"])
            self._bufferAppend("/Height %d" % imgDesc["height"])
            for extraInfo in imgDesc["extraInfos"]:
                self._bufferAppend(extraInfo)

            if "extraObjects" in imgDesc and len(imgDesc["extraObjects"])>0:
                extraObjectCount = self.objectCount + 1
                for extraObjectKey, extraObjectValue \
                    in imgDesc["extraObjects"].items():

                    self._bufferAppend("/%s %d 0 R" \
                        % (extraObjectKey, extraObjectCount))
                    extraObjectCount += 1


            self._bufferAppend("/Length %d>>" % len(imgDesc["data"]))
            self._bufferAppend('stream')
            self._bufferAppend(imgDesc["data"])
            self._bufferAppend('endstream')
            self._bufferAppend("endobj")

            if "extraObjects" in imgDesc and len(imgDesc["extraObjects"])>0:
                for extraObjectKey, extraObjectValue in imgDesc["extraObjects"].items():
                    self._addNewObject()
                    self._bufferAppend("<<", endLine="")

                    for i,line in enumerate(extraObjectValue["Keys"]):
                        if i == len(extraObjectValue["Keys"]) - 1:
                            self._bufferAppend(line, endLine="")
                        else:
                            self._bufferAppend(line)

                    self._bufferAppend(">>")
                    self._bufferAppend('stream')
                    self._bufferAppend(extraObjectValue["Stream"])
                    self._bufferAppend('endstream')
                    self._bufferAppend("endobj")

    def _addTrueTypeFonts(self):
        """
        Helper (private) function to embed each font (plus the default Helvetica
        font) on the PDF buffer.
        """
        for fontName, fontDesc in self.fonts.items():
            if fontDesc["fontType"] != "TrueType":
                # Only TrueType fonts are embedded (for now). Helvetica (for
                # example) will be handled later.
                continue

            # Creation of the font prefix, used by PDF readers for the font
            # merging (in case of multiple font subsettings).
            prefix = ""
            offset = 0
            rest = fontDesc["fontId"]
            while(rest>0):
                mod = rest%26
                prefix = chr(65 + mod)+ prefix
                rest = rest // 26
                offset += 1
            while(offset < 2):
                prefix = "A"+ prefix
                offset += 1
            prefix = "PaPDF" + prefix

            prefixedFontName = "%s+%s" % (prefix, fontName)

            # Preparation of the font subset and retrieval of the font metrics:
            ttp = TrueType.TrueTypeParser(fontDesc["fileName"])
            trueTypeData = ttp.getEmbeddingData(fontDesc["usedCharacters"])

            pdfFontDescKeys = ["Ascent", "Descent", "CapHeight", "Flags", \
                "FontBBox", "ItalicAngle", "StemV", "MissingWidth"]
            pdfFontDescKeyValues = {}
            for k in pdfFontDescKeys:
                pdfFontDescKeyValues[k] = trueTypeData["fontDesc"][k]

            fontCharWidths = trueTypeData["charWidths"]
            maxChar = trueTypeData["maxChar"]
            defaultCharWidth = trueTypeData["defaultCharWidth"]
            ttfCodeToGlyph = trueTypeData["charToGlyph"]

            ttfSubsetStream = trueTypeData["subsetStream"]
            ttfCompressedSubsetStream = zlib.compress(ttfSubsetStream)

            #Update the font object reference, now that we know its value:
            self.fonts[fontName]["fontObjectReference"] = self.objectCount + 1

            # Adding the font with subtype Type0, this section contains a
            # reference to the CIDFontType2 (\DescendantFonts) but also the
            # encoding used (Identity-H - see PDF Reference, section 5.9)
            self._addNewObject()
            self._bufferAppend("<</Type /Font")
            self._bufferAppend("/Subtype /Type0")
            self._bufferAppend("/BaseFont /" + prefixedFontName + "")
            self._bufferAppend("/Encoding /Identity-H")
            self._bufferAppend("/DescendantFonts [" \
                + str(self.objectCount+1) + " 0 R]")
            self._bufferAppend("/ToUnicode " + str(self.objectCount+2) + " 0 R")
            self._bufferAppend(">>")
            self._bufferAppend("endobj")

            # The next section will need the size of each character, they are
            # thus computed here: the syntax is described in section 5.6 from
            # the PDF Reference ("Glyph Metrics in CIDFonts" subsection).
            #
            # Below, 1 is the index of start and the following array specifies
            # the width of consecutive chars:
            charWidths = " 1 [" # the chars in the range 1,31 have a width 0
            computed2 = []
            for c in range(1, maxChar+1):
                val = int(round(fontCharWidths[c],0))
                if val >= 65535:
                    val = 0
                computed2.append(str(val))
            charWidths +=" ".join(computed2) + " ]\n"


            # Adding the font with subtype CIDFontType2
            self._addNewObject()
            self._bufferAppend("<</Type /Font")
            self._bufferAppend("/Subtype /CIDFontType2")
            self._bufferAppend("/BaseFont /" + prefixedFontName + "")
            self._bufferAppend("/CIDSystemInfo " \
                + str(self.objectCount+2) + " 0 R")
            self._bufferAppend("/FontDescriptor " \
                + str(self.objectCount+3) + " 0 R")
            self._bufferAppend("/DW %d" % int(round(defaultCharWidth)))
            self._bufferAppend("/W [%s]" % charWidths)
            self._bufferAppend("/CIDToGIDMap " \
                + str(self.objectCount + 4) + " 0 R")
            self._bufferAppend(">>")
            self._bufferAppend("endobj")


            # Magic dictionary to encode the glyphs in unicode, taken and
            # simplified from Example 5.16 in the PDF standard
            self._addNewObject()
            toUnicodeStream = "/CIDInit /ProcSet findresource begin\n" \
                + "12 dict begin\n" \
                + "begincmap\n" \
                + "/CIDSystemInfo\n" \
                + "<</Registry (Adobe)\n" \
                + "/Ordering (UCS)\n" \
                + "/Supplement 0\n" \
                + ">> def\n" \
                + "/CMapName /Adobe-Identity-UCS def\n" \
                + "/CMapType 2  def\n" \
                + "1 beginbfrange\n" \
                + "<0000> <FFFF> <0000>\n" \
                + "endbfrange\n" \
                + "1 begincodespacerange\n" \
                + "<0000> <FFFF>\n" \
                + "endcodespacerange\n" \
                + "1 beginbfchar\n" \
                + "<0000> <FFFF>\n" \
                + "endbfchar\n" \
                + "endcmap\n" \
                + "CMapName currentdict /CMap defineresource pop\n" \
                + "end\n" \
                + "end"

            filter = ""
            if self.compress:
                filter = "/Filter /FlateDecode "
                toUnicodeStream = zlib.compress(toUnicodeStream.encode())

            self._bufferAppend("<<" + filter + "/Length " \
                + str(len(toUnicodeStream)) + ">>")
            self._bufferAppend("stream")
            self._bufferAppend(toUnicodeStream)
            self._bufferAppend("endstream")
            self._bufferAppend("endobj")

            # Adding the CIDSystemInfo object, to define a character collection.
            self._addNewObject()
            self._bufferAppend("<</Registry (Adobe)")
            self._bufferAppend("/Ordering (UCS)")
            self._bufferAppend("/Supplement 0")
            self._bufferAppend(">>")
            self._bufferAppend("endobj")

            # The font descriptor is appended to the PDF buffer.
            self._addNewObject()
            self._bufferAppend("<</Type /FontDescriptor")
            self._bufferAppend("/FontName /" + prefixedFontName)
            for key, value in pdfFontDescKeyValues.items():
                self._bufferAppend(" /%s %s" % (key, str(value)))
            self._bufferAppend("/FontFile2 " + str(self.objectCount + 2) + " 0 R")
            self._bufferAppend(">>")
            self._bufferAppend("endobj")

            # The next section defines the mapping of chars to glyphs, encoded
            # on two bytes per char:
            charToGlyph = ["\x00"] * (65536*2)
            for currChar, currGlyph in ttfCodeToGlyph.items():
                # Shift and mask to expand into two bytes:
                charToGlyph[currChar * 2] = chr(currGlyph >> 8)
                charToGlyph[currChar * 2 + 1] = chr(currGlyph & 0xFF)
            charToGlyph = "".join(charToGlyph).encode("latin1")
            charToGlyph = zlib.compress(charToGlyph)
            self._addNewObject()
            self._bufferAppend("<</Length " + str(len(charToGlyph)) + "")
            self._bufferAppend("/Filter /FlateDecode")
            self._bufferAppend(">>")
            self._bufferAppend("stream")
            self._bufferAppend(charToGlyph)
            self._bufferAppend("endstream")
            self._bufferAppend("endobj")

            # Addint the font subset data to the PDF buffer:
            self._addNewObject()
            self._bufferAppend("<</Length " + str(len(ttfCompressedSubsetStream)))
            self._bufferAppend("/Filter /FlateDecode")
            self._bufferAppend("/Length1 " + str(len(ttfSubsetStream)))
            self._bufferAppend(">>")
            self._bufferAppend("stream")
            self._bufferAppend(ttfCompressedSubsetStream)
            self._bufferAppend("endstream")
            self._bufferAppend("endobj")

        # Adding the default Helvetica font (and possible other variants like
        # Helvetica-Bold that were added on demand, by the setFont() method).
        for fontName, fontDesc in self.fonts.items():
            if fontName.lower().startswith("helvetica"):
                self.fonts[fontName]["fontObjectReference"] = self.objectCount + 1
                fontId = len(self.fonts.items())
                self._addNewObject()
                self._bufferAppend("<</Type /Font")
                self._bufferAppend("/Subtype /Type1")
                self._bufferAppend("/BaseFont /" + fontName)
                self._bufferAppend("/Encoding /WinAnsiEncoding")
                self._bufferAppend(">>")
                self._bufferAppend("endobj")

    def _addAppendix(self):
        """
        Helper (private) function to add the PDF appendix to the PDF buffer.
        """

        # First, we add the page root:
        self.offsets[1] = len(self.buffer)
        self._bufferAppend("1 0 obj")
        self._bufferAppend("<</Type /Pages")
        kids = "/Kids ["
        for i in range(1, self.pageId+2):
            kids += str(2*i + 1) + " 0 R "
        self._bufferAppend(kids + "]")
        self._bufferAppend("/Count " + str(self.pageId+1))
        # Page size definition:
        self._bufferAppend("/MediaBox [0 0 %.2f %.2f]" \
            % (PaPDF.MM_TO_DPI*self.w_mm, PaPDF.MM_TO_DPI*self.h_mm))
        self._bufferAppend(">>")
        self._bufferAppend("endobj")


        # Adding the fonts to the PDF buffer:
        self._addTrueTypeFonts()
        self._addImageStreams()
        self._addShadingObjects()
        self._addExtGStateObjects()

        # Adding the references:
        self.offsets[2]=len(self.buffer)
        self._bufferAppend("2 0 obj")
        self._bufferAppend("<<")
        self._bufferAppend("/ProcSet [/PDF /Text /ImageB /ImageC /ImageI]")
        self._bufferAppend("/Font <<")

        # Sorting the references requires a second (temporary) dictionary:
        fontReferences = {}
        for fontName, fontDesc in self.fonts.items():
            i = fontDesc["fontId"]
            objectCount = fontDesc["fontObjectReference"]
            fontReferences[i+1] = objectCount

        fontReferences = collections.OrderedDict(sorted(fontReferences.items()))
        for fontId, objectCount in fontReferences.items():
            self._bufferAppend("/F"+str(fontId)+" "+str(objectCount)+" 0 R")
        self._bufferAppend(">>")

        # Adding the images:
        self._bufferAppend("/XObject <<")
        imageIdToFontRef = {}
        for _, imgDesc in self.images.items():
            imageIdToFontRef[imgDesc["imageId"]] = \
            imgDesc["fontObjectReference"]
        for id, ref in imageIdToFontRef.items():
            self._bufferAppend("/I%d %d 0 R" % (id, ref))
        self._bufferAppend(">>")


        # Adding the Shading Objects:
        for shadingObject in self.shadingObjects:
            self._bufferAppend("/Shading << /Sh%d %d 0 R >>" \
                % (shadingObject["shadingObjectId"], \
                    shadingObject["shadingObjectReference"]))

        for extGStateObject in self.extGStateObjects:
            self._bufferAppend("/ExtGState << /GS%d %d 0 R >>" \
                % (extGStateObject["extGStateObjectId"], \
                    extGStateObject["extGStateObjectReference"]))

        self._bufferAppend(">>")
        self._bufferAppend("endobj")

        # Adding the information on the PDF extra metadata fields:
        self._addNewObject()
        self._bufferAppend("<<")
        self._out_prefix_paren("Producer", PaPDF.PROGRAM_NAME)
        self._out_prefix_paren("Title", self.title)
        # Todo: add support for the other metadata :
        # ["Subject", "Author", "Keywords", "Creator"]
        now = str(datetime.now().strftime("%Y%m%d%H%M%S"))
        self._out_prefix_paren("CreationDate", "D:%s" % now)
        self._bufferAppend(">>")
        self._bufferAppend("endobj")

        # Adding the PDF catalog:
        self._addNewObject()
        self._bufferAppend("<<")
        self._bufferAppend("/Type /Catalog")
        self._bufferAppend("/Pages 1 0 R")
        self._bufferAppend("/OpenAction [3 0 R /FitH null]")
        self._bufferAppend("/PageLayout /OneColumn")
        self._bufferAppend(">>")
        self._bufferAppend("endobj")


        # Adding the cross-references table:
        crossReferenceOffset = len(self.buffer)
        self._bufferAppend("xref")
        self._bufferAppend("0 " + str(self.objectCount+1))
        self._bufferAppend("0000000000 65535 f ")
        for i in range(1, self.objectCount+1):
            self._bufferAppend("%010d 00000 n " % (self.offsets[i]))

        # Finally, adding the trailer (and the EOF) at the end of the PDF buffer
        self._bufferAppend("trailer")
        self._bufferAppend("<<")
        self._bufferAppend("/Size "+str(self.objectCount+1))
        self._bufferAppend("/Root "+str(self.objectCount)+" 0 R")
        self._bufferAppend("/Info "+str(self.objectCount-1)+" 0 R")
        self._bufferAppend(">>")
        self._bufferAppend("startxref")
        self._bufferAppend(crossReferenceOffset)
        self._bufferAppend("%%EOF")

    def close(self):
        """
        Close the PDF and write to the file, given its filename.
        """
        self._flushPageStream()
        self._addAppendix()
        with open(self.filename,"wb") as f:
            f.write(self.buffer)
