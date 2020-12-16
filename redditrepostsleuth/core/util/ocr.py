from typing import Text, List

import cv2
import numpy as np
import requests
from imutils.object_detection import non_max_suppression
from matplotlib import pyplot as plt

from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.util.imagehashing import generate_img_by_url
import pytesseract

def predictions(prob_score, geo, min_confidence: float = 0.5):
    (numR, numC) = prob_score.shape[2:4]
    boxes = []
    confidence_val = []

    # loop over rows
    for y in range(0, numR):
        scoresData = prob_score[0, 0, y]
        x0 = geo[0, 0, y]
        x1 = geo[0, 1, y]
        x2 = geo[0, 2, y]
        x3 = geo[0, 3, y]
        anglesData = geo[0, 4, y]

        # loop over the number of columns
        for i in range(0, numC):
            if scoresData[i] < min_confidence:
                continue

            (offX, offY) = (i * 4.0, y * 4.0)

            # extracting the rotation angle for the prediction and computing the sine and cosine
            angle = anglesData[i]
            cos = np.cos(angle)
            sin = np.sin(angle)

            # using the geo volume to get the dimensions of the bounding box
            h = x0[i] + x2[i]
            w = x1[i] + x3[i]

            # compute start and end for the text pred bbox
            endX = int(offX + (cos * x1[i]) + (sin * x2[i]))
            endY = int(offY - (sin * x1[i]) + (cos * x2[i]))
            startX = int(endX - w)
            startY = int(endY - h)

            boxes.append((startX, startY, endX, endY))
            confidence_val.append(scoresData[i])

    # return bounding boxes and associated confidence_val
    return (boxes, confidence_val)


def get_image_text(url: Text):
    from google.cloud import vision
    client = vision.ImageAnnotatorClient()
    image = vision.types.Image()
    image.source.image_uri = url

    response = client.text_detection(image=image)

    if response.error.message:
        raise Exception(
            '{}\nFor more info on error messages, check: '
            'https://cloud.google.com/apis/design/errors'.format(
                response.error.message))
    else:
        return response.full_text_annotation.text

def get_image_text_tesseract(
        url: Text,
        east_model: Text,
        height: int = 1280,
        width: int = 1280,
        padding: float = 0.06,
        draw_results:  bool = False):

    resp = requests.get(url, stream=True).raw
    image = np.asarray(bytearray(resp.read()), dtype="uint8")
    image = cv2.imdecode(image, cv2.IMREAD_COLOR)
    (origH, origW) = image.shape[:2]
    log.debug('Original Image Size: %s', image.shape[:2])
    if origH < height:
        aspect = origW / origH
        newW = 32 * round((height * aspect) / 32)
        image = cv2.resize(image, (newW, height))
    else:
        aspect = origW / origH
        corrected_height = 32 * round(origH / 32)
        newW = 32 * round((corrected_height * aspect) / 32)
        image = cv2.resize(image, (newW, corrected_height))

    log.debug('Adjusted Image Size: %s', image.shape[:2])
    (H, W) = image.shape[:2]

    # construct a blob from the image to forward pass it to EAST model
    blob = cv2.dnn.blobFromImage(image, 1.0, (W, H),
                                 (123.68, 116.78, 103.94), swapRB=True, crop=False)


    image = get_grayscale(image)
    # orig = cv2.GaussianBlur(orig,(5,5),0)
    # orig = cv2.bitwise_not(orig)
    image = bilat_filter(image)
    # orig = remove_noise(orig)
    image = adaptive_thresholding(image)

    (origH, origW) = image.shape[:2]

    net = cv2.dnn.readNet(east_model)

    # The following two layer need to pulled from EAST model for achieving this.
    layerNames = [
        "feature_fusion/Conv_7/Sigmoid",
        "feature_fusion/concat_3"]

    # Forward pass the blob from the image to get the desired output layers
    net.setInput(blob)
    (scores, geometry) = net.forward(layerNames)
    (boxes, confidence_val) = predictions(scores, geometry)
    boxes = non_max_suppression(np.array(boxes), probs=confidence_val)

    ##Text Detection and Recognition

    # initialize the list of results
    results = []

    # loop over the bounding boxes to find the coordinate of bounding boxes
    for (startX, startY, endX, endY) in boxes:
        # scale the coordinates based on the respective ratios in order to reflect bounding box on the original image
        startX = int(startX)
        startY = int(startY)
        endX = int(endX)
        endY = int(endY)

        dX = int((endX - startX) * padding)
        dY = int((endY - startY) * padding)

        startX = max(0, startX - dX)
        startY = max(0, startY - dY)
        endX = min(origW, endX + (dX * 2))
        endY = min(origH, endY + (dY * 2))

        # extract the region of interest
        r = image[startY:endY, startX:endX]

        # configuration setting to convert image to string.
        configuration = ("-l eng --oem 1 --psm 8")
        ##This will recognize the text from the image of bounding box
        text = pytesseract.image_to_string(r, config=configuration)

        # append bbox coordinate and associated text to the list of results
        results.append(((startX, startY, endX, endY), text))
        print(text)

    if draw_results:
        orig_image = image.copy()
        for ((start_X, start_Y, end_X, end_Y), text) in results:
            # display the text detected by Tesseract
            print("{}\n".format(text))

            # Displaying text
            text = "".join([x if ord(x) < 128 else "" for x in text]).strip()
            cv2.rectangle(orig_image, (start_X, start_Y), (end_X, end_Y),
                          (0, 0, 255), 2)
            cv2.putText(orig_image, text, (start_X, start_Y - 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        plt.imshow(orig_image, cmap='Greys_r')
        # plt.imshow(orig, cmap='Greys_r')
        plt.title('Output')
        plt.show()

    return build_results_string(results), image

def build_results_string(results: List) -> Text:
    result = ""
    for r in results:
        result += r[1].replace('\n\f', ' ')
    return result

def get_grayscale(image):
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


# noise removal
def remove_noise(image):
    return cv2.medianBlur(image, 5)


# thresholding
def thresholding(image):
    return cv2.threshold(image, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

def adaptive_thresholding(image):
    return cv2.adaptiveThreshold(image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 2)

def bilat_filter(image):
    return cv2.bilateralFilter(image, 9, 75, 75)

# dilation
def dilate(image):
    kernel = np.ones((5, 5), np.uint8)
    return cv2.dilate(image, kernel, iterations=1)

def get_histo(image):
    return cv2.calcHist(image, [0], None, [256], [0,256])

# erosion
def erode(image):
    kernel = np.ones((5, 5), np.uint8)
    return cv2.erode(image, kernel, iterations=1)


# opening - erosion followed by dilation
def opening(image):
    kernel = np.ones((5, 5), np.uint8)
    return cv2.morphologyEx(image, cv2.MORPH_OPEN, kernel)


# canny edge detection
def canny(image):
    return cv2.Canny(image, 100, 200)

