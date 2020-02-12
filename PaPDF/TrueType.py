import os, sys
from datetime import datetime
from collections import OrderedDict
import struct

# Simple TrueType library, developed using the Apple Developer's TrueType
# Reference Manual. This document can be found under:
# https://developer.apple.com/fonts/TrueType-Reference-Manual/

class ByteStream:
    # Helper class to deal with the bytes from a TrueType file.
    # The TrueType types definition can be found in the TrueType Reference, on
    # chapter 6, "Font Tables" -> "Introduction".
    def __init__(self, fileObject):
        self.fileObject = fileObject

    def readBytes(self, numBytes=2, unsigned=True):
        # Read numBytes in a signed or unsigned manner and return as an integer
        data = self.fileObject.read(numBytes)
        output = 0
        for i in range(0, numBytes):
            output += (data[i] << (8*(numBytes-1-i)))
        if not unsigned and (output & (1 << 8*numBytes-1)):
            # Reversing the two's complement:
            output -= (1 << 8*numBytes)
        return output;

    def readString(self, numChars, encoding="latin-1"):
        # Return a read sting of numChars character
        return self.fileObject.read(numChars).decode(encoding)

    def readArray(self, arrayLength, numBytes=2, unsigned=True):
        # Read a sequence of `arrayLength` integers of `numBytes` (in a signed
        # or unsigned manner, depending on `unsigned`) and return a python list
        # of integers
        array = []
        for i in range(arrayLength):
            array.append(self.readBytes(numBytes))
        return array

    def readDateTime(self):
        # Retruns a read TrueType 'longDateTime' date type a python datetime
        #
        # The long internal format of a date in seconds since 12:00 midnight,
        # January 1, 1904. It is represented as a signed 64-bit integer.
        # 24107 is the number of days betwen UNIX Epoch and the PDF Epoch.
        timestamp = self.readBytes(8) - 24107 * 24 * 3600
        return datetime.fromtimestamp(timestamp)

    def read16Dot16FixedPointNumber(self, roundingDecimals=4):
        # Return a read TrueType 'Fixed' fixed-point number
        magnitude = self.readBytes(2, unsigned=False)
        fraction = self.readBytes(2)
        output = magnitude
        for i in range(0, 16):
            output += (fraction & 0x01) * 2 ** (-16+i)
            fraction >>= 1
        return round(output, roundingDecimals)

    @staticmethod
    def computeChecksum(data):
        # Helper function to compute the checksum of UINT32 values:
        if len(data)%4 != 0:
            # Padding in case of too short data:
            data += bytes([0x00]* (4-len(data)%4))
        sum = 0
        for i in range(0, len(data)-1, 4):
            sum += struct.unpack(">L", data[i:i+4])[0]
        return sum & 0xFFFFFFFF


class TrueTypeParser:
    # Reference: https://developer.apple.com/fonts/TrueType-Reference-Manual/

    def __init__(self, fileName):
        self.fileName = fileName;
        self.embeddingData = None;

    def getEmbeddingData(self, charSubset):
        # Return the font data used to embed the font in a PDF

        # Simple caching, in case of function reuse.
        if self.embeddingData is not None:
            return self.embeddingData

        # Sorting the charSubset:
        charSubsetList = list(charSubset)
        charSubsetList.sort()
        charSubset = set(charSubsetList)


        # If the data is not cached, it needs to be parsed from the TTF file:
        with open(self.fileName, "rb") as f:
            byteStream = ByteStream(f)
            version = byteStream.readBytes(4)
            if version not in [0x74727565, 0x00010000]:
                # The values 'true' (0x74727565) and 0x00010000 are recognized
                # by OS X and iOS as referring to TrueType fonts.
                raise("The given file does not seem to be a TrueType font " \
                    + "file (incorrect TrueType version detected - " + version \
                    + ")")

            # Reading the offset subtable:
            # uint16 	numTables 	    number of tables
            # uint16 	searchRange 	(maximum power of 2 <= numTables)*16
            # uint16 	entrySelector 	log2(maximum power of 2 <= numTables)
            # uint16 	rangeShift    	numTables*16-searchRange
            tables = {}
            numTables = byteStream.readBytes(2)
            searchRange = byteStream.readBytes(2)
            entrySelector = byteStream.readBytes(2)
            rangeShift = byteStream.readBytes(2)

            for i in range(numTables):
                #  Reading each table directory:
                # uint32 	tag 	    4-byte identifier
                # uint32 	checkSum 	checksum for this table
                # uint32 	offset 	    offset from beginning of sfnt
                # uint32 	length   	length of this table in byte (actual
                #                       length not padded length)
                tag = byteStream.readString(4)
                record = {}
                record['checksum'] = (byteStream.readBytes(2),
                    byteStream.readBytes(2))
                record['offset'] = byteStream.readBytes(4)
                record['length'] = byteStream.readBytes(4)
                tables[tag] = record

            # Consuming the head table:
            f.seek(tables["head"]["offset"])
            headVersion = byteStream.read16Dot16FixedPointNumber()
            if headVersion != 1:
                raise Exception("Bad TrueType version in the header table: " \
                    + "version = %d" % headVersion)
            fontRevision = byteStream.read16Dot16FixedPointNumber()
            f.seek(4, os.SEEK_CUR)

            magicNumber = byteStream.readBytes(4)
            if magicNumber != 1594834165:
                raise Exception("Bad TrueType magicNumber in the header table:"\
                    + " magicNumber= %d" % magicNumber)
            flags = byteStream.readBytes(2)
            unitsPerEm = byteStream.readBytes(2)
            created = byteStream.readDateTime()
            modified = byteStream.readDateTime()

            xMin = round(byteStream.readBytes(2, unsigned=False) * 1000.0 \
                    // float(unitsPerEm), 0)
            yMin = round(byteStream.readBytes(2, unsigned=False) * 1000.0 \
                    // float(unitsPerEm), 0)
            xMax = round(byteStream.readBytes(2, unsigned=False) * 1000.0 \
                    // float(unitsPerEm), 0)
            yMax = round(byteStream.readBytes(2, unsigned=False) * 1000.0 \
                    // float(unitsPerEm), 0)
            bbox = [xMin, yMin, xMax, yMax]
            macStyle = byteStream.readBytes(2)
            lowestRecPPEM = byteStream.readBytes(2)
            fontDirectionHint = byteStream.readBytes(2, unsigned=False)
            indexToLocFormat = byteStream.readBytes(2, unsigned=False)
            glyphDataFormat = byteStream.readBytes(2, unsigned=False)


            # Consuming the cmap table:
            f.seek(tables["cmap"]["offset"])
            cmapTableVersion = byteStream.readBytes(2)
            if cmapTableVersion != 0:
                raise Exception("Bad TrueType cmapTableVersion in the cmap " \
                    + "table: cmapTableVersion = %d (and should be 0)" \
                    % cmapTableVersion)
            cmapTablesQuantity = byteStream.readBytes(2)


            # Parsing each cmap encoding subtable:
            # Defining two local variable constants to avoid implicit errors in
            # case of a future extension of this library with more CMAP formats.
            CMAP_ENCODING_FORMAT_4 = "CMAP_ENCODING_FORMAT_4"
            CMAP_ENCODING_FORMAT_12 = "CMAP_ENCODING_FORMAT_12"
            cmapFormatCandidats = {
                CMAP_ENCODING_FORMAT_4 : [],
                CMAP_ENCODING_FORMAT_12 : [],
            }
            for cmapSubtableId in range(cmapTablesQuantity):
                platformID = byteStream.readBytes(2)
                platformSpecificID = byteStream.readBytes(2)
                offset = byteStream.readBytes(4)

                currOffset = f.seek(0, os.SEEK_CUR)
                f.seek(tables["cmap"]["offset"] + offset)
                cmapFormat = byteStream.readBytes(2);
                f.seek(currOffset);
                # 'cmap' Platforms
                # 0 	Unicode 	Indicates Unicode version.
                # 1 	Macintosh 	Script Manager code.
                # 2 	(reserved; do not use)
                # 3 	Microsoft 	Microsoft encoding.
                if platformID not in [0,1,3]:
                    continue
                    # platformID values other than 0, 1, or 3 are allowed but
                    # cmaps using them will be ignored.

                encoding = None
                if platformID == 0: # Unicode
                    # Unicode Platform-specific Encoding Identifiers
                    # 0 	Default semantics
                    # 1 	Version 1.1 semantics
                    # 2 	ISO 10646 1993 semantics (deprecated)
                    # 3 	Unicode 2.0 or later semantics (BMP only)
                    # 4 	Unicode 2.0 or later semantics (non-BMP characters
                    #           allowed)
                    # 5 	Unicode Variation Sequences
                    # 6 	Full Unicode coverage (used with type 13.0 cmaps by
                    #           OpenType)
                    if cmapFormat == 4:
                        cmapFormatCandidats[CMAP_ENCODING_FORMAT_4] \
                            .append(tables["cmap"]["offset"] + offset)
                elif platformID == 1: # Macintosh
                    pass
                elif platformID == 3: # Windows
                    # Windows Platform-specific Encoding Identifiers
                    # 0 	Symbol
                    # 1 	Unicode BMP-only (UCS-2)
                    # 2 	Shift-JIS
                    # 3 	PRC
                    # 4 	BigFive
                    # 5 	Johab
                    # 10 	Unicode UCS-4
                    if platformSpecificID == 1 and cmapFormat == 4:
                        cmapFormatCandidats[CMAP_ENCODING_FORMAT_4] \
                            .append(tables["cmap"]["offset"] + offset)
                    elif platformSpecificID == 10 and cmapFormat == 4:
                        cmapFormatCandidats[CMAP_ENCODING_FORMAT_12] \
                            .append(tables["cmap"]["offset"] + offset)

            charToGlyph = {}
            glyphToChar = {}
            maxChar = 0
            if len(cmapFormatCandidats[CMAP_ENCODING_FORMAT_12]) > 0:
                cmapFormatOffset = \
                    cmapFormatCandidats[CMAP_ENCODING_FORMAT_12][0]
                self.seek(cmapFormatOffset)
                format = byteStream.read16Dot16FixedPointNumber()
                # According to the doc: Format number is set to 12, let's check:
                if format != 12.0:
                    raise Exception("Wrong cmap format 12, format field")
                length = byteStream.readBytes(4)
                language = byteStream.readBytes(4)
                nGroups= byteStream.readBytes(4)
                for groupId in range(grpCount):
                    startCharCode = byteStream.readBytes(4)
                    endCharCode = byteStream.readBytes(4)
                    startGlyphCode = byteStream.readBytes(4)
                    for charId in range(startCharCode, endCharCode + 1):
                        charToGlyph[charId] = startGlyphCode \
                            + (charId-startCharCode)
                        if charId> maxChar and charId < 0x30000:
                            maxChar = charId
                        if not glyph in glyphToChar:
                            glyphToChar[glyph] = []
                        glyphToChar[glyph].append(currChar)
            elif len(cmapFormatCandidats[CMAP_ENCODING_FORMAT_4]) > 0:
                cmapFormatOffset = \
                    cmapFormatCandidats[CMAP_ENCODING_FORMAT_4][0]
                f.seek(cmapFormatOffset)
                format = byteStream.readBytes(2)
                # According to the doc: Format number is set to 4, let's check:
                if format != 4:
                    raise Exception("Wrong cmap format 4, format field")
                length = byteStream.readBytes(2)
                language = byteStream.readBytes(2)
                segCount = byteStream.readBytes(2) // 2
                 # Skipping searchRange, entrySelector and rangeShift:
                f.seek(3*2, os.SEEK_CUR)

                endCode = []
                for i in range(segCount):
                    endCode.append(byteStream.readBytes(2))

                reservedPad = byteStream.readBytes(2)
                # According to the doc: This value should be zero, let's check:
                if reservedPad != 0:
                    raise Exception("Wrong cmap format 4, reservedPad field")

                startCode = []
                for i in range(segCount):
                    startCode.append(byteStream.readBytes(2))

                idDelta = []
                for i in range(segCount):
                    idDelta.append(byteStream.readBytes(2))

                idRangeOffsetStart = f.seek(0, os.SEEK_CUR)
                idRangeOffset = []
                for i in range(segCount):
                    idRangeOffset.append(byteStream.readBytes(2))

                currOffset = f.seek(0, os.SEEK_CUR)
                for n in range(segCount):
                    for currChar in range(startCode[n], endCode[n]+1):
                        glyph = 0
                        if idRangeOffset[n] == 0:
                            glyph = 0xFFFF & (currChar + idDelta[n])
                        else:
                            offset = idRangeOffsetStart + 2 * n \
                                + (currChar - startCode[n]) * 2 \
                                + idRangeOffset[n]
                            if offset < cmapFormatOffset + length:
                                f.seek(offset)
                                glyph = byteStream.readBytes(2);
                                if (glyph != 0):
                                    glyph += idDelta[n] & 0xFFFF
                        charToGlyph[currChar] = glyph
                        if currChar> maxChar and currChar < 0x30000:
                            maxChar = currChar
                        if not glyph in glyphToChar:
                            glyphToChar[glyph] = []
                        glyphToChar[glyph].append(currChar)
                f.seek(currOffset);
            else:
                raise Exception("Unable to find a supported CMAP encoding in " \
                    + "the given font file. ")

            # Consuming the hhea table:
            f.seek(tables["hhea"]["offset"])
            hheaVersion = byteStream.read16Dot16FixedPointNumber()
            ascent = byteStream.readBytes(2, unsigned=False) * 1000.0 \
                    // float(unitsPerEm)
            descent = byteStream.readBytes(2, unsigned=False) * 1000.0 \
                    // float(unitsPerEm)
            lineGap = byteStream.readBytes(2, unsigned=False)
            advanceWidthMax = byteStream.readBytes(2)
            minLeftSideBearing = byteStream.readBytes(2, unsigned=False)
            minRightSideBearing = byteStream.readBytes(2, unsigned=False)
            xMaxExtent = byteStream.readBytes(2, unsigned=False)
            caretSlopeRise = byteStream.readBytes(2, unsigned=False)
            caretSlopeRun = byteStream.readBytes(2, unsigned=False)
            caretOffset = byteStream.readBytes(2, unsigned=False)
            f.seek(5*2, os.SEEK_CUR)
            numOfLongHorMetrics = byteStream.readBytes(2)

            # Consuming the OS/2 table, if provided:
            sCapHeight = ascent
            usWeightClass = 500
            if "OS/2" in tables:
                f.seek(tables["OS/2"]["offset"])
                version = byteStream.readBytes(2)
                xAvgCharWidth = byteStream.readBytes(2, unsigned=False)
                usWeightClass = byteStream.readBytes(2)
                f.seek(82, os.SEEK_CUR)
                if version > 1:
                    sCapHeight = byteStream.readBytes(2, unsigned=False) \
                        * 1000.0 // float(unitsPerEm)

            stemV = 50 + int(pow((usWeightClass / 65.0),2))

            # Consuming the post table:
            f.seek(tables["post"]["offset"])
            f.seek(4, os.SEEK_CUR)
            italicAngle = byteStream.read16Dot16FixedPointNumber();
            underlinePosition = byteStream.readBytes(2) * 1000.0 \
                    // float(unitsPerEm)
            underlineThickness = byteStream.readBytes(2) * 1000.0 \
                    // float(unitsPerEm)
            isFixedPitch = byteStream.readBytes(4);

            ttfflags = 4
            if italicAngle != 0:
                ttfflags |= 64
            if usWeightClass >= 600:
                ttfflags |= 0x40000
            if isFixedPitch is not 0:
                ttfflags |= 1

            # Consuming the maxp table:
            f.seek(tables["maxp"]["offset"])
            version = byteStream.read16Dot16FixedPointNumber()
            numGlyphs = byteStream.readBytes(2)

            # Consuming the hmtx table:
            f.seek(tables["hmtx"]["offset"])
            charQuantity = 0
            defaultCharWidth = byteStream.readBytes(2) * 1000 \
                // float(unitsPerEm)
            _ = byteStream.readBytes(2)

            roundedUpLength = (((maxChar + 1) // 1024) + 1) * 1024
            charWidths = [defaultCharWidth] * roundedUpLength
            for glyphId in range(1, numOfLongHorMetrics):
                advanceWidth = byteStream.readBytes(2)
                leftSideBearing = byteStream.readBytes(2)
                if glyphId not in glyphToChar:
                    continue
                for charId in glyphToChar[glyphId]:
                    if(charId>0 and charId<0xFFFF):
                        currCharWidth = int(round(
                            advanceWidth * 1000 // float(unitsPerEm)))

                        if currCharWidth == 0:
                            currCharWidth = 65535
                        if charId < 0x30000:
                            charWidths[charId] = currCharWidth
                            charQuantity += 1
            charWidths[0] = charQuantity

            # Consuming the loca table:
            f.seek(tables["loca"]["offset"])
            glyphOffset = []
            locaOffsets = []

            offsetRatio = 1
            if indexToLocFormat == 0:
                locaOffsets = byteStream.readArray(numGlyphs+1, 2)
                offsetRatio = 2
            elif indexToLocFormat == 1:
                locaOffsets = byteStream.readArray(numGlyphs+1, 4)
            else:
                raise Exception("Unimplemented indexToLocFormat while parsing "
                    + "the loca table.")
            for n in range(numGlyphs):
                glyphOffset.append(locaOffsets[n]*offsetRatio)

            subsetCharToGlyph = {}
            subsetMaxChar = 0
            for currChar in charSubset:
                if (currChar in charToGlyph):
                    subsetCharToGlyph[currChar] = charToGlyph[currChar]
                    if currChar > subsetMaxChar and currChar < 0x30000:
                        subsetMaxChar = currChar

            startGlyphOffset = tables["glyf"]["offset"]
            subsetTableData = OrderedDict()
            # format: tablename => data (in bytes)

            # Copying the standard table:
            for tableName in ["name", "cvt", "fpgm", "prep", "gasp", "post"]:
                if tableName in tables:
                    f.seek(tables[tableName]["offset"])
                    subsetTableData[tableName] = \
                        f.read(tables[tableName]["length"])

            # Grouping the subsetCharToGlyph by continuous groups:
            continuousSubsetCharToGlyph = OrderedDict()
            sortedSubsetCharToGlyph = list(subsetCharToGlyph.items())
            sortedSubsetCharToGlyph.sort()


            # Consuming the glyf table to add Compound glyphs:
            compoundGlyphs = []
            startGlyfOffset = tables["glyf"]["offset"]
            for char, glyph in subsetCharToGlyph.items():
                f.seek(startGlyfOffset + glyphOffset[glyph])
                numberOfContours = byteStream.readBytes(2, unsigned=False)
                if numberOfContours < 0:
                    f.seek(8, os.SEEK_CUR)
                    while True:
                        flags = byteStream.readBytes(2)
                        glyphIndex = byteStream.readBytes(2)
                        # If arguments are words, we skip 4 bytes else 2:
                        seekOffset = 84 if (flags & 0x0001) else 2
                        f.seek(seekOffset, os.SEEK_CUR)

                        # Depending on  the scale, we skip 2, 4 or 8 bytes
                        seekOffset = 2 if (flags & 0x0008) else \
                            4 if (flags & 0x0040) else 8 \
                                if (flags & 0x0080) else 0
                        f.seek(seekOffset, os.SEEK_CUR)

                        compoundGlyphs.append((1, glyphIndex))
                        if not (flags & 0x0020):
                            break # if no more glyfs, we break

            subsetGlyphToId = OrderedDict()
            for id,(char, glyph) in enumerate(sortedSubsetCharToGlyph):
                subsetGlyphToId[glyph] = id

            if len(sortedSubsetCharToGlyph)>0:
                lastChar = sortedSubsetCharToGlyph[0][0]
                lastGroup = [sortedSubsetCharToGlyph[0][1]]
                groupChar = lastChar
                for char, glyph in sortedSubsetCharToGlyph[1:]:
                    if char-lastChar == 1: # continuous
                        lastGroup.append(glyph)
                    else:
                        continuousSubsetCharToGlyph[groupChar] = lastGroup.copy()
                        lastGroup = [glyph]
                        groupChar = char
                    lastChar = char
                continuousSubsetCharToGlyph[groupChar] = lastGroup.copy()

            sortedSubsetCharToGlyph += compoundGlyphs
            # Creating the "cmap" table:
            # UInt16 	version 	Version number (Set to zero)
            # UInt16 	numberSubtables 	Number of encoding subtables
            # ==> Values = 0(magic number), 1
            #
            # UInt16 	platformID 	Platform identifier
            # UInt16 	platformSpecificID 	Platform-specific encoding id
            # UInt32 	offset 	Offset of the mapping table
            # ==> Values = 3,1,0,12 (offset=12, over UInt32)
            #
            # 'cmap' format 4 subtable:
            #   UInt16 	format 	Format number is set to 4
            #   UInt16 	length 	Length of subtable in bytes
            #   UInt16 	language 	Language code (see above)
            #   UInt16 	segCountX2 	2 * segCount
            #   UInt16 	searchRange 	2 * (2**FLOOR(log2(segCount)))
            #   UInt16 	entrySelector 	log2(searchRange/2)
            #   UInt16 	rangeShift 	(2 * segCount) - searchRange
            #   UInt16 	endCode[segCount] 	Ending character code for each
            #       segment, last = 0xFFFF.
            #   UInt16 	reservedPad 	This value should be zero
            #   UInt16 	startCode[segCount] 	Starting character code for each
            #       segment
            #   UInt16 	idDelta[segCount] 	Delta for all character codes in
            #       segment
            #   UInt16 	idRangeOffset[segCount] 	Offset in bytes to glyph
            #       indexArray, or 0
            #   UInt16 	glyphIndexArray[variable] 	Glyph index array

            numGlyphs = numberOfHMetrics = len(sortedSubsetCharToGlyph)+1

            #  endCode requires a last segment as 0xFFFF (read above), hence +1:
            segCount = len(continuousSubsetCharToGlyph)+1
            length = 16 + (8*segCount ) + (numGlyphs+1)

            searchRange = 1
            entrySelector = 0
            while searchRange*2 <= segCount:
                searchRange = searchRange*2
                entrySelector = entrySelector+1
            searchRange *= 2
            rangeShift = segCount * 2 - searchRange

            cmap = [0, 1,
                3, 1, 0, 12,
                # 'cmap' format 4 subtable:
                4, length, 0, segCount*2, searchRange, entrySelector,rangeShift,
                ]

            # adding endCode[segCount]:
            for char, values  in continuousSubsetCharToGlyph.items():
                endCode = char + len(values) - 1
                cmap.append(endCode)
            #  endCode requires a last segment as 0xFFFF:
            cmap.append(0xFFFF)
            # reservedPad
            cmap.append(0)

            # adding startCode[segCount]:
            for char, _  in continuousSubsetCharToGlyph.items():
                cmap.append(char)
            cmap.append(0xFFFF) # last segment

            # adding idDelta[segCount]:
            for char, values  in continuousSubsetCharToGlyph.items():
                firstCharId = subsetGlyphToId[values[0]]
                cmap.append(firstCharId-char + 1) # +1 for the first segment
            cmap.append(1) # last segment delta is 1

            # adding idRangeOffset[segCount]:
            #+1 for the last segment:
            for _ in range(len(continuousSubsetCharToGlyph)+1):
                cmap.append(0) # no offset


            # Putting the range values:
            for char, values  in continuousSubsetCharToGlyph.items():
                cmap.extend([subsetGlyphToId[v]+1 for v in values])
            cmap.append(0)

            cmapBytes = b""
            for cm in cmap:
                if cm>=0:
                    cmapBytes += struct.pack(">H", cm) # H: unsigned short
                else:
                    cmapBytes += struct.pack(">h", cm) # h: signed short
            subsetTableData["cmap"] = cmapBytes


            f.seek(tables["glyf"]["offset"])
            glyfData = f.read(tables["glyf"]["length"])

            newGlyfData = b""
            newHmtxData = b""
            newLocaData = b""
            locaOffsets = [0]
            currOffset = 0

            glyphToIndex = {}
            for id, (char, glyph) in enumerate(sortedSubsetCharToGlyph):
                glyphToIndex[glyph] = id + 1 # + 1 to count the (0.0)
                    # first element of sortedSubsetCharToGlyph

            # Artificially adding a (0,0) char/glyph tuple, for code simplicity:
            for char, glyph in [(0,0)] + sortedSubsetCharToGlyph:
                # Updating the new hmtx table:
                f.seek(tables["hmtx"]["offset"] + glyph*4)
                newHmtxData += f.read(4)

                # Updating the new glyf table:
                glyphPos = glyphOffset[glyph]
                glyphLen = 0
                if glyph+1 < len(glyphOffset):
                    glyphLen = glyphOffset[glyph+1] - glyphPos

                if glyphLen > 0:
                    currGlyphData = bytearray(glyfData[glyphPos:glyphPos+glyphLen])
                    numberOfContours = struct.unpack(">h", currGlyphData[0:2])[0]
                    if numberOfContours<0:
                        glyfOffset = 10
                        moreGlyphs = True

                        while moreGlyphs:
                            flags = struct.unpack(">h", \
                                currGlyphData[glyfOffset:glyfOffset+2])[0]
                            moreGlyphs = flags &  (1 << 5)

                            glyphIndex = struct.unpack(">h", \
                                currGlyphData[glyfOffset+2:glyfOffset+4])[0]
                            newGlyphId = glyphToIndex[glyphIndex]
                            currGlyphData[glyfOffset+2:glyfOffset+4] = \
                                struct.pack(">H", newGlyphId)

                            # Depending on  the flags, we increment the offset:
                            glyfOffset += 4
                            glyfOffset += 4 if (flags & 0x0001) else 2
                            glyfOffset += 2 if (flags & 0x0008) else \
                                4 if (flags & 0x0040) else 8 \
                                    if (flags & 0x0080) else 0
                else:
                    currGlyphData = b''


                # Adding padding:
                if len(currGlyphData)%4!=0:
                    # Padding in case of too short data:
                    paddingLength = 4-len(currGlyphData)%4
                    currGlyphData += bytes([0x00] * paddingLength)
                    currOffset += paddingLength
                newGlyfData += currGlyphData
                currOffset += glyphLen
                locaOffsets.append(currOffset)

            # Preparing the loca data:
            ratio = 0.5
            format = ">H"
            if indexToLocFormat == 1:
                ratio = 1
                format = ">L"
            for locaOffset in locaOffsets:
                newLocaData += struct.pack(format, int(locaOffset * ratio))

            # Putting the tables data in the subsetTableData:
            subsetTableData["glyf"] = newGlyfData
            subsetTableData["hmtx"] = newHmtxData
            subsetTableData["loca"] = newLocaData

            # Adding and then updating the remaining tables:
            for tableName in ["head", "hhea", "maxp", "OS/2"]:
                if tableName in tables:
                    f.seek(tables[tableName]["offset"])
                    subsetTableData[tableName] = \
                        f.read(tables[tableName]["length"])

            # Update of the new fields:
            subsetTableData["head"] = bytearray(subsetTableData["head"])
            subsetTableData["head"][8:12] = [0x00]*4 #checkSumAdjustment
            subsetTableData["head"][50:52] = struct.pack(">H",indexToLocFormat)
            subsetTableData["head"] = bytes(subsetTableData["head"])

            subsetTableData["hhea"] = bytearray(subsetTableData["hhea"])
            subsetTableData["hhea"][34:36] = struct.pack(">H",numberOfHMetrics)
            subsetTableData["hhea"] = bytes(subsetTableData["hhea"])

            subsetTableData["maxp"] = bytearray(subsetTableData["maxp"])
            subsetTableData["maxp"][4:6] = struct.pack(">H",numGlyphs)
            subsetTableData["maxp"] = bytes(subsetTableData["maxp"])

            # Replacing the post table by its shortest version, using Format 3:
            # Format 3 makes it possible to create a special font that is not
            # burdened with a large 'post' table set of glyph names. This format
            # specifies that no PostScript name information is provided for the
            # glyphs in this font. The printing behavior of this format on
            # PostScript printers is unspecified, except that it should not
            # result in a fatal or unrecoverable error. (...)
            # This format does not require a special subtable.

            postFormat = 3 # format 3 is a short post table.
            # Below it is written as an uint16, followed by 16 zero bits, for
            # complying with the 16.16  bit signed required by the `format`
            # table field (cheap trick, since only postFormat = 3 is supported).
            subsetTableData["post"] = bytearray(subsetTableData["post"])
            subsetTableData["post"][0:4] = struct.pack(">HH", postFormat, 0)
            subsetTableData["post"][16:32] = [0x00] * 16
            # We remove the trailing subtable, as it is not needed in Format 3:
            subsetTableData["post"] = subsetTableData["post"][:32]
            subsetTableData["post"] = bytes(subsetTableData["post"])


            # Preparing the offset subtable (first table, before the offset dir)
            numTables = len(subsetTableData)
            searchRange = 1
            entrySelector = 0
            while searchRange * 2 <= numTables:
                searchRange = searchRange * 2
                entrySelector = entrySelector + 1

            searchRange = searchRange * 16
            rangeShift = numTables * 16 - searchRange
            trueTypeFontConstant = 0x00010000

            offsetSubtableData = struct.pack(">LHHHH", trueTypeFontConstant,
                numTables, searchRange, entrySelector, rangeShift)


            # Note on checksums: According to the official documentation
            # (see chapitre 6 on the official documentation), each table should
            # contain its own checksum.
            # However the head table need to be a-posteriory updated with its
            # field `checkSumAdjustment` recomputed. First we treat each table
            # the same and then we adjust the `checkSumAdjustment` field using
            # the provided magic number (B1B0AFBA).
            tableDirectoryData = b""
            offset = 12 + numTables * 16
            headOffset = -1
            for tableName, tableData in sorted(subsetTableData.items()):
                if tableName == "head":
                    headOffset = offset
                currData = b""
                currData += tableName.encode("latin1")
                currData += \
                    struct.pack(">L", ByteStream.computeChecksum(tableData))
                currData += struct.pack(">LL", offset, len(tableData))
                tableDirectoryData += currData
                offset += (len(tableData) + 3) & ~3

            for tableName, tableData in sorted(subsetTableData.items()):
                tableData += b'\x00\x00\x00'
                incr = tableData[0:len(tableData) & ~3]
                tableDirectoryData += incr

            output = bytearray(offsetSubtableData + tableDirectoryData)

            # Adjusting `checkSumAdjustment` field of the head table:
            checksum = 0xB1B0AFBA - ByteStream.computeChecksum(output)
            output[headOffset + 8:headOffset + 12] = struct.pack(">L", 0xFFFFFFFF & checksum)
            output = bytes(output)

            charToGlyph = {}
            for id,(char, glyph) in enumerate(sortedSubsetCharToGlyph):
                charToGlyph[char] = id+1

            self.embeddingData = {
                "defaultCharWidth": defaultCharWidth,
                "charToGlyph": charToGlyph,
                "maxChar": maxChar,
                "charWidths": charWidths,
                "fontDesc": {
                    "Ascent": ascent,
                    "Descent": descent,
                    "CapHeight": sCapHeight,
                    "Flags": (ttfflags | 4) & ~32,
                    "FontBBox": "[%d %d %d %d]" % (*bbox,),
                    "ItalicAngle": italicAngle,
                    "StemV": stemV,
                    "MissingWidth": defaultCharWidth,
                },
                "subsetStream": output,
            }
        return self.embeddingData
