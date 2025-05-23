import pdf2image
import numpy as np
import layoutparser as lp

# Define PDF file path
pdf_file = r"/home/barath-kumar/Downloads/boilers act.pdf" # Adjust the filepath accordingly

# Convert PDF to image
img = np.asarray(pdf2image.convert_from_path(pdf_file)[1])

model = lp.Detectron2LayoutModel(
            config_path = "lp://PrimaLayout/mask_rcnn_R_50_FPN_3x/config", # In model catalog
            label_map   = {1:"TextRegion", 2:"TableRegion", 3:"SeparatorRegion", 4:"OtherRegion"}, # In model`label_map`
            extra_config=["MODEL.ROI_HEADS.SCORE_THRESH_TEST", 0.4] # Optional
        )
layout=model.detect(img)
# lp.draw_box(img,layout)

for block in layout:
    print("Type:", block.type)
    print("Score:", block.score)
    print("Coordinates:", block.coordinates)  # [x1, y1, x2, y2]
    print("Bounding Box:", block.block)       # Or block.block.to_tuple()
    print("---")
