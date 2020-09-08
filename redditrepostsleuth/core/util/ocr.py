from typing import Text

from redditrepostsleuth.core.util.imagehashing import generate_img_by_url
import pytesseract

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

def get_image_text_tesseract(url: Text):
    img = generate_img_by_url(url)
    result = pytesseract.image_to_string(img)
    print(result)
    return result