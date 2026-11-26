import CoreGraphics
import CryptoKit
import Foundation

struct ValidatedJPEG: Sendable {
    let width: Int
    let height: Int
    let components: Int
    let profile: Data
    let intent: String?
    let interpolate: Bool
    let fingerprint: SHA256.Digest

    init?(_ data: Data, image: CGImage) {
        guard let components = jpegComponents(data),
              let colorSpace = image.colorSpace,
              colorSpace.model == (components == 1 ? .monochrome : .rgb),
              let profile = colorSpace.copyICCData() else { return nil }
        width = image.width
        height = image.height
        self.components = components
        self.profile = profile as Data
        switch image.renderingIntent {
        case .absoluteColorimetric: intent = "AbsoluteColorimetric"
        case .relativeColorimetric: intent = "RelativeColorimetric"
        case .perceptual: intent = "Perceptual"
        case .saturation: intent = "Saturation"
        default: intent = nil
        }
        interpolate = image.shouldInterpolate
        fingerprint = SHA256.hash(data: data)
    }
}

// Restrict passthrough to 8-bit baseline/progressive gray and unambiguous YCbCr.
// JFIF and the Adobe marker agree with PDF's DCTDecode defaults for these files.
private func jpegComponents(_ data: Data) -> Int? {
    data.withUnsafeBytes { (bytes: UnsafeRawBufferPointer) -> Int? in
        guard bytes.count >= 4, bytes[0] == 0xff, bytes[1] == 0xd8,
              bytes[bytes.count - 2] == 0xff, bytes[bytes.count - 1] == 0xd9 else { return nil }
        var position = 2
        var components = 0
        var jfif = false
        var adobeTransform: UInt8?
        while position + 4 <= bytes.count, bytes[position] == 0xff {
            let marker = bytes[position + 1]
            let length = Int(bytes[position + 2]) * 256 + Int(bytes[position + 3])
            let payload = position + 4
            let end = position + 2 + length
            guard length >= 2, end <= bytes.count else { return nil }
            switch marker {
            case 0xc0, 0xc2: // Start of frame
                guard components == 0, length >= 8, bytes[payload] == 8 else { return nil }
                components = Int(bytes[payload + 5])
                guard length == 8 + components * 3 else { return nil }
                if components == 3 {
                    guard bytes[payload + 6] == 1, bytes[payload + 9] == 2,
                          bytes[payload + 12] == 3 else { return nil }
                }
            case 0xe0 where length >= 7: // JFIF
                jfif = jfif || bytes[payload..<(payload + 5)].elementsEqual([74, 70, 73, 70, 0])
            case 0xee where length >= 7: // Adobe APP14
                if bytes[payload..<(payload + 5)].elementsEqual("Adobe".utf8) {
                    guard length >= 14, adobeTransform == nil else { return nil }
                    adobeTransform = bytes[payload + 11]
                }
            case 0xda: // Start of scan
                if components == 1, adobeTransform ?? 0 == 0 { return 1 }
                if components == 3, adobeTransform == 1 || (adobeTransform == nil && jfif) { return 3 }
                return nil
            default: break
            }
            position = end
        }
        return nil
    }
}

func writeJPEGChapter(_ images: Zip2Sequence<[URL], [ValidatedJPEG]>, to url: URL) throws -> Bool {
    guard FileManager.default.createFile(atPath: url.path, contents: nil) else {
        throw MangapyError("Could not create PDF")
    }
    let file = try FileHandle(forWritingTo: url)
    defer { try? file.close() }
    var pdf = JPEGChapterPDF(file: file)
    try pdf.write("%PDF-1.4\n")
    try file.write(contentsOf: Data([0x25, 0xe2, 0xe3, 0xcf, 0xd3, 0x0a]))
    for (url, jpeg) in images {
        let data = try Data(contentsOf: url)
        // Recheck the bytes without decoding if a staging file was replaced.
        guard SHA256.hash(data: data) == jpeg.fingerprint else { return false }
        try pdf.addPage(jpeg, data: data)
    }
    return try pdf.finish()
}

private struct JPEGChapterPDF {
    let file: FileHandle
    // Object zero is free. Reserve objects one and two for the catalog and page tree.
    private var offsets: [UInt64] = [0, 0, 0]
    private var profiles: [Data: Int] = [:]
    private var pages: [Int] = []

    init(file: FileHandle) {
        self.file = file
    }

    func write(_ text: String) throws {
        try file.write(contentsOf: Data(text.utf8))
    }

    private mutating func object(_ body: String, stream: Data? = nil, id: Int? = nil) throws -> Int {
        let number = id ?? offsets.count
        let offset = try file.offset()
        if let id { offsets[id] = offset }
        else { offsets.append(offset) }
        try write("\(number) 0 obj\n<< \(body)")
        if let stream {
            try write(" /Length \(stream.count) >>\nstream\n")
            try file.write(contentsOf: stream)
            try write("\nendstream\n")
        } else {
            try write(" >>\n")
        }
        try write("endobj\n")
        return number
    }

    mutating func addPage(_ jpeg: ValidatedJPEG, data: Data) throws {
        let profile: Int
        if let existing = profiles[jpeg.profile] {
            profile = existing
        } else {
            let alternate = jpeg.components == 1 ? "DeviceGray" : "DeviceRGB"
            profile = try object("/N \(jpeg.components) /Alternate /\(alternate)", stream: jpeg.profile)
            profiles[jpeg.profile] = profile
        }
        let width = pdfPoints(jpeg.width)
        let height = pdfPoints(jpeg.height)
        let imageIntent = jpeg.intent.map { " /Intent /\($0)" } ?? ""
        let drawIntent = jpeg.intent.map { "/\($0) ri " } ?? ""
        let image = try object("""
            /Type /XObject /Subtype /Image /Width \(jpeg.width) /Height \(jpeg.height)
            /BitsPerComponent 8 /ColorSpace [/ICCBased \(profile) 0 R]
            /Interpolate \(jpeg.interpolate) /Filter /DCTDecode\(imageIntent)
            """, stream: data)
        let drawing = "q \(drawIntent)\(width) 0 0 \(height) 0 0 cm /Im Do Q\n"
        let content = try object("", stream: Data(drawing.utf8))
        let page = try object("""
            /Type /Page /Parent 2 0 R /MediaBox [0 0 \(width) \(height)]
            /Resources << /XObject << /Im \(image) 0 R >> >> /Contents \(content) 0 R
            """)
        pages.append(page)
    }

    mutating func finish() throws -> Bool {
        _ = try object("/Type /Catalog /Pages 2 0 R", id: 1)
        let kids = pages.map { "\($0) 0 R" }.joined(separator: " ")
        _ = try object("/Type /Pages /Count \(pages.count) /Kids [\(kids)]", id: 2)
        let start = try file.offset()
        guard start <= 9_999_999_999 else { return false } // Classic xref uses fixed-width offsets.
        try write("xref\n0 \(offsets.count)\n0000000000 65535 f \n")
        for offset in offsets.dropFirst() {
            let number = String(offset)
            try write("\(String(repeating: "0", count: 10 - number.count))\(number) 00000 n \n")
        }
        try write("trailer\n<< /Size \(offsets.count) /Root 1 0 R >>\nstartxref\n\(start)\n%%EOF\n")
        return true
    }
}

private func pdfPoints(_ pixels: Int) -> String {
    let hundredths = pixels * 72
    return "\(hundredths / 100).\(String(format: "%02d", hundredths % 100))"
}
