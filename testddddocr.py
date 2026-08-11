import ddddocr

ocr = ddddocr.DdddOcr()
image = open("0556.png", "rb").read()

# 设置识别范围为数字
ocr.set_ranges(0)  # 等同于 ocr.set_ranges("0123456789")

result = ocr.classification(image)
print(result)
