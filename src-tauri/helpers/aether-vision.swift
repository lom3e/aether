import Foundation
import Vision
import AppKit

// aether-vision ocr <image.png> [--lang it-IT,en-US]
// Prints JSON: {"width":W,"height":H,"words":[{"text":..,"x":..,"y":..,"w":..,"h":..}]} with boxes normalised 0..1, origin top-left.
struct Word: Codable { let text: String; let x: Double; let y: Double; let w: Double; let h: Double }
struct Out: Codable { let width: Int; let height: Int; let words: [Word] }

func fail(_ m: String) -> Never { FileHandle.standardError.write((m + "\n").data(using: .utf8)!); exit(2) }
let args = CommandLine.arguments
guard args.count >= 3, args[1] == "ocr" else { fail("usage: aether-vision ocr <image> [--lang it-IT,en-US]") }
guard let img = NSImage(contentsOfFile: args[2]), let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { fail("cannot read image") }
var langs = ["it-IT", "en-US"]
if let i = args.firstIndex(of: "--lang"), i + 1 < args.count { langs = args[i + 1].split(separator: ",").map(String.init) }
var words: [Word] = []
let req = VNRecognizeTextRequest { r, _ in
    for obs in (r.results as? [VNRecognizedTextObservation]) ?? [] {
        guard let cand = obs.topCandidates(1).first else { continue }
        let s = cand.string
        // One box per whitespace-separated token so a secret can be hidden without hiding the whole line.
        var idx = s.startIndex
        while idx < s.endIndex {
            while idx < s.endIndex, s[idx].isWhitespace { idx = s.index(after: idx) }
            if idx == s.endIndex { break }
            var end = idx
            while end < s.endIndex, !s[end].isWhitespace { end = s.index(after: end) }
            let range = idx..<end
            if let box = try? cand.boundingBox(for: range) {
                let b = box.boundingBox
                words.append(Word(text: String(s[range]), x: b.minX, y: 1 - b.maxY, w: b.width, h: b.height))
            }
            idx = end
        }
    }
}
req.recognitionLevel = .accurate
req.recognitionLanguages = langs
req.usesLanguageCorrection = false
do { try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req]) } catch { fail("ocr failed") }
let out = Out(width: cg.width, height: cg.height, words: words)
FileHandle.standardOutput.write(try! JSONEncoder().encode(out))
