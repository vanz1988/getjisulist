import sys
import os
import numpy as np
import torch
import torch.nn as nn
from PIL import Image, ImageEnhance
import cv2
import pytesseract

IMG_SIZE = 32
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'model.pt')
model = None


class DigitCNN(nn.Module):
    def __init__(self):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(1, 16, 3, padding=1),
            nn.BatchNorm2d(16), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(16, 32, 3, padding=1),
            nn.BatchNorm2d(32), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(32, 64, 3, padding=1),
            nn.BatchNorm2d(64), nn.ReLU(), nn.MaxPool2d(2),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Dropout(0.3),
            nn.Linear(64 * 4 * 4, 128),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(128, 10),
        )

    def forward(self, x):
        return self.classifier(self.features(x))


def _load_model():
    global model
    if model is None:
        model = DigitCNN()
        model.load_state_dict(torch.load(MODEL_PATH, map_location='cpu'))
        model.eval()
        if torch.backends.mps.is_available():
            model = model.to('mps')
    return model


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
            split_x = None
            if mean_dark > 0:
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
            else:
                mid = cw // 2
                all_boxes.append((x, y, mid, ch))
                all_boxes.append((x + mid, y, cw - mid, ch))
            continue
        all_boxes.append(box)
    all_boxes.sort(key=lambda b: b[0])
    return all_boxes


def _detect_slant(img):
    w, h = img.size
    best_angle = 0
    best_score = -1
    for angle in range(-30, 31, 5):
        if angle == 0:
            img_rot = img
        else:
            img_rot = img.rotate(angle, expand=True, fillcolor=(255, 255, 255))
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
            if len(boxes) == 4:
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
    return best_angle


def _detect_boxes(img_final):
    w_f, h_f = img_final.size
    best_data = None
    for thresh in [80, 100, 120, 140]:
        for scale in [6, 8, 10, 12]:
            img_large = img_final.resize((w_f * scale, h_f * scale), Image.LANCZOS)
            img_c = ImageEnhance.Contrast(img_large).enhance(3.0).convert('L')
            img_bw = img_c.point(lambda x: 0 if x < thresh else 255)
            boxes = _find_char_boxes(img_bw, erode=False)
            if len(boxes) < 4:
                boxes_e = _find_char_boxes(img_bw, erode=True)
                min_w = max(10, int(w_f * scale * 0.03))
                boxes = [b for b in boxes_e if b[2] > min_w and b[3] > min_w]
            if len(boxes) == 4:
                best_data = (img_bw, 4, boxes, scale, thresh)
                break
            elif len(boxes) > 4 and (best_data is None or len(boxes) < best_data[1]):
                best_data = (img_bw, len(boxes), boxes, scale, thresh)
    if best_data:
        img_bw, _, boxes, _, _ = best_data
        boxes = _split_wide_boxes(img_bw, boxes)
    else:
        img_large = img_final.resize((w_f * 10, h_f * 10), Image.LANCZOS)
        img_c = ImageEnhance.Contrast(img_large).enhance(3.0).convert('L')
        img_bw = img_c.point(lambda x: 0 if x < 140 else 255)
        boxes = _find_char_boxes(img_bw)
        boxes = _split_wide_boxes(img_bw, boxes)
    return img_bw, boxes


def _preprocess(crop):
    dark = np.array(crop.convert('L') if crop.mode != 'L' else crop) < 128
    rows = np.where(dark.any(axis=1))[0]
    cols = np.where(dark.any(axis=0))[0]
    if len(rows) == 0 or len(cols) == 0:
        return None
    trimmed = np.array(crop.convert('L'))[rows[0]:rows[-1]+1, cols[0]:cols[-1]+1]
    h, w = trimmed.shape
    pad = max(0, IMG_SIZE - max(h, w)) // 2
    padded = np.pad(trimmed, ((pad, pad), (pad, pad)), mode='constant', constant_values=255)
    padded = cv2.resize(padded, (IMG_SIZE, IMG_SIZE))
    return (padded.astype(np.float32) - 128) / 128


def _infer_digit(model, proc):
    if proc is None:
        return '?', 0.0
    device = 'mps' if torch.backends.mps.is_available() else 'cpu'
    tensor = torch.FloatTensor(proc).unsqueeze(0).unsqueeze(0).to(device)
    with torch.no_grad():
        output = model(tensor)
        softmax = torch.softmax(output, dim=1)
        _, predicted = output.max(1)
        return str(predicted.item()), softmax[0][predicted.item()].item()


def ocr_digits(image_path):
    model = _load_model()
    img = Image.open(image_path).convert('RGB')

    slant = _detect_slant(img)
    img_final = img if slant == 0 else img.rotate(slant, expand=True, fillcolor=(255, 255, 255))

    img_bw, boxes = _detect_boxes(img_final)

    result = ''
    for i, (x, y, cw, ch) in enumerate(boxes):
        pad = 20
        crop = img_bw.crop((max(0, x - pad), max(0, y - pad),
                             min(img_bw.width, x + cw + pad),
                             min(img_bw.height, y + ch + pad)))
        proc = _preprocess(crop)
        digit, prob = _infer_digit(model, proc)
        result += digit
    return result


if __name__ == '__main__':
    img_path = sys.argv[1] if len(sys.argv) > 1 else '/Users/vanz/Downloads/duanjuscript/index.png'
    print(ocr_digits(img_path))