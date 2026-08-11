import sys
import numpy as np
from PIL import Image, ImageEnhance, ImageOps
import cv2
os.environ['FLAGS_use_mkldnn'] = '0'
import pytesseract
from paddleocr import PaddleOCR

_PADdleOCR = None

def _get_ocr():
    global _PADdleOCR
    if _PADdleOCR is None:
        _PADdleOCR = PaddleOCR(lang='en', use_textline_orientation=False)
    return _PADdleOCR

def _find_char_boxes(img_bw, erode=False):
    arr = np.array(img_bw)
    if erode:
        kernel = np.ones((3, 3), np.uint8)
        arr = cv2.erode(arr, kernel, iterations=1)
    _, t = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(t, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        if cw > 5 and ch > 5:
            boxes.append((x, y, cw, ch))
    boxes.sort(key=lambda b: b[0])
    return boxes

def _try_full_image_tesseract(img, w, h):
    results = {}
    for contrast in [1.5, 2.0, 2.5, 3.0]:
        for thresh in [80, 100, 120, 140]:
            for scale in [4, 6, 8, 10]:
                img_large = img.resize((w * scale, h * scale), Image.LANCZOS)
                img_c = ImageEnhance.Contrast(img_large).enhance(contrast).convert('L')
                img_bw = img_c.point(lambda x, t=thresh: 0 if x < t else 255)
                text = pytesseract.image_to_string(
                    img_bw, config='--psm 7 -c tessedit_char_whitelist=0123456789').strip()
                if text.isdigit() and len(text) >= 4:
                    results[text] = results.get(text, 0) + 1
    if results:
        best = max(results, key=results.get)
        if results[best] >= 4:
            return best
    return None

def _count_holes(crop):
    arr = np.array(crop.convert('L') if crop.mode != 'L' else crop)
    _, thresh = cv2.threshold(arr, 128, 255, cv2.THRESH_BINARY)
    contours, hierarchy = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    holes = 0
    if hierarchy is not None:
        for h in hierarchy[0]:
            if h[3] != -1:
                holes += 1
    return holes

def _split_wide_boxes(img_bw, boxes):
    if not boxes:
        return boxes
    widths = sorted([b[2] for b in boxes])
    median_w = widths[len(widths) // 2]
    all_boxes = []
    for box in boxes:
        x, y, cw, ch = box
        if cw > median_w * 1.8:
            crop = img_bw.crop((x, y, x + cw, y + ch))
            arr = np.array(crop)
            dark_mask = arr < 128
            col_dark = dark_mask.sum(axis=0)
            mean_dark = col_dark.mean()
            if mean_dark > 0:
                split_x = None
                for gt in [0.05, 0.10, 0.15, 0.20]:
                    gaps = np.where(col_dark < mean_dark * gt)[0]
                    if len(gaps) > 1:
                        diffs = np.diff(gaps)
                        if len(diffs) > 0:
                            split_x = gaps[np.argmax(diffs)]
                            break
                if split_x is not None:
                    all_boxes.append((x, y, split_x, ch))
                    all_boxes.append((x + split_x, y, cw - split_x, ch))
                    continue
            mid = cw // 2
            all_boxes.append((x, y, mid, ch))
            all_boxes.append((x + mid, y, cw - mid, ch))
            continue
        all_boxes.append(box)
    all_boxes.sort(key=lambda b: b[0])
    return all_boxes

def ocr_digits(image_path):
    ocr = _get_ocr()
    img = Image.open(image_path).convert('RGB')
    w, h = img.size

    # Step 1: Slant detection with compactness scoring
    best_angle = 0
    best_score = -1
    best_data = None

    for angle in range(-30, 31, 5):
        if angle == 0:
            img_rot = img
        else:
            img_rot = img.rotate(angle, expand=False, fillcolor=(255, 255, 255))
        w_r, h_r = img_rot.size

        for thresh in [80, 100, 120, 140]:
            img_large = img_rot.resize((w_r * 8, h_r * 8), Image.LANCZOS)
            img_c = ImageEnhance.Contrast(img_large).enhance(3.0).convert('L')
            img_bw = img_c.point(lambda x: 0 if x < thresh else 255)
            boxes = _find_char_boxes(img_bw, erode=False)

            if len(boxes) < 4:
                boxes_e = _find_char_boxes(img_bw, erode=True)
                min_w = max(8, int(w_r * 8 * 0.03))
                boxes = [b for b in boxes_e if b[2] > min_w and b[3] > min_w]

            if len(boxes) >= 4:
                densities = []
                for (bx, by, bw_, bh_) in boxes:
                    crop_ = img_bw.crop((bx, by, bx + bw_, by + bh_))
                    arr_ = np.array(crop_)
                    dark_ = (arr_ < 128).sum()
                    total_ = bw_ * bh_
                    densities.append(dark_ / total_ if total_ > 0 else 0)
                score = sum(densities) / len(densities)
                if score > best_score:
                    best_score = score
                    best_angle = angle
                    best_data = (angle, thresh)

    img_final = img if best_angle == 0 else img.rotate(best_angle, expand=True, fillcolor=(255, 255, 255))

    # Step 2: Full-image tesseract
    full_result = _try_full_image_tesseract(img, w, h)
    if full_result:
        print(f'  full-image: [{full_result}]')
        return full_result

    if best_angle != 0:
        full_result = _try_full_image_tesseract(img_final, img_final.size[0], img_final.size[1])
        if full_result:
            print(f'  full-image rotated: [{full_result}]')
            return full_result

    # Step 3: Find best preprocessing for char detection
    best_data = None
    w_f, h_f = img_final.size

    for thresh in [100, 120, 140, 80]:
        for scale in [12, 10, 8, 6]:
            img_large = img_final.resize((w_f * scale, h_f * scale), Image.LANCZOS)
            img_c = ImageEnhance.Contrast(img_large).enhance(3.0).convert('L')
            img_bw = img_c.point(lambda x: 0 if x < thresh else 255)
            boxes = _find_char_boxes(img_bw, erode=False)
            if len(boxes) < 4:
                boxes_e = _find_char_boxes(img_bw, erode=True)
                min_w = max(10, int(w_f * scale * 0.04))
                boxes = [b for b in boxes_e if b[2] > min_w and b[3] > min_w]
            if len(boxes) >= 4:
                if best_data is None or len(boxes) > best_data[1]:
                    best_data = (img_bw, len(boxes), boxes, scale, thresh)
                break

    if best_data:
        img_bw, _, boxes, _, _ = best_data
    else:
        img_large = img_final.resize((w_f * 10, h_f * 10), Image.LANCZOS)
        img_c = ImageEnhance.Contrast(img_large).enhance(3.0).convert('L')
        img_bw = img_c.point(lambda x: 0 if x < 140 else 255)
        boxes = _find_char_boxes(img_bw)

    boxes = _split_wide_boxes(img_bw, boxes)

    print(f'  完整图失败，逐字符 (slant={best_angle})')

    # Step 4: Char-level OCR
    result = ''
    for i, (x, y, cw, ch) in enumerate(boxes):
        pad = 20
        crop = img_bw.crop((max(0, x - pad), max(0, y - pad),
                             min(img_bw.width, x + cw + pad),
                             min(img_bw.height, y + ch + pad)))

        crop_base = crop.resize((crop.width * 3, crop.height * 3), Image.LANCZOS)
        crop_base = ImageOps.expand(crop_base, 30, fill=255)

        dc = {}
        for zoom in [1, 2]:
            if zoom > 1:
                tmp = crop_base.resize((crop_base.width * 2, crop_base.height * 2), Image.LANCZOS)
            else:
                tmp = crop_base
            for angle in [0, 5, 10, 15, 20, -5, -10, -15, -20]:
                rotated = tmp.rotate(angle, expand=True, fillcolor=255)
                text = pytesseract.image_to_string(
                    rotated, config='--psm 10 -c tessedit_char_whitelist=0123456789').strip()
                if text.isdigit():
                    dc[text] = dc.get(text, 0) + 1

        if dc:
            tess_best = max(dc, key=dc.get)
            tess_total = sum(dc.values())
            tess_ratio = dc[tess_best] / tess_total

            # Hole counting for 8/6/3 disambiguation (always check)
            holes = _count_holes(crop)
            if tess_best in ('6', '8') and holes >= 2:
                tess_best = '8'
                tess_ratio = 1.0
            elif tess_best in ('6', '8') and holes == 0:
                tess_best = '3'
                tess_ratio = 1.0

            crop_big2 = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
            crop_big2 = ImageOps.expand(crop_big2, 30, fill=255)
            paddle_best = ('', 0)
            for angle in [0, 10, 20, -10, -20]:
                rotated = crop_big2.rotate(angle, expand=True, fillcolor=255)
                rotated.save('/tmp/ocr_tmp.png')
                res = ocr.predict('/tmp/ocr_tmp.png')
                for r in res:
                    if r['rec_texts'] and r['rec_scores'][0] > paddle_best[1]:
                        t = r['rec_texts'][0]
                        if t.strip().isdigit():
                            paddle_best = (t, r['rec_scores'][0])

            if tess_ratio >= 0.85:
                digit = tess_best
            elif paddle_best[1] >= 0.95 and paddle_best[0]:
                digit = paddle_best[0]
            elif tess_ratio >= 0.5:
                digit = tess_best
            else:
                digit = paddle_best[0] if paddle_best[0] else tess_best

            print(f'  char{i}: [{digit}] tess={tess_best}({dc.get(tess_best,0)}/{tess_total}) paddle={paddle_best[0]}({paddle_best[1]:.2f})')
        else:
            crop_big2 = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
            crop_big2 = ImageOps.expand(crop_big2, 30, fill=255)
            paddle_best = ('', 0)
            for angle in [0, 10, 20, -10, -20]:
                rotated = crop_big2.rotate(angle, expand=True, fillcolor=255)
                rotated.save('/tmp/ocr_tmp.png')
                res = ocr.predict('/tmp/ocr_tmp.png')
                for r in res:
                    if r['rec_texts'] and r['rec_scores'][0] > paddle_best[1]:
                        t = r['rec_texts'][0]
                        if t.strip().isdigit():
                            paddle_best = (t, r['rec_scores'][0])
            digit = paddle_best[0] if paddle_best[0] else '?'
            print(f'  char{i}: [{digit}] paddle={paddle_best[0]}({paddle_best[1]:.2f})')

        result += digit
    return result


if __name__ == '__main__':
    img_path = sys.argv[1] if len(sys.argv) > 1 else '/Users/vanz/Downloads/duanjuscript/index.png'
    result = ocr_digits(img_path)
    print(result)
