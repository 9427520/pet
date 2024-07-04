from PIL import Image, ImageEnhance, ExifTags

def enhance_image(image):
    enhancer = ImageEnhance.Sharpness(image)
    image = enhancer.enhance(2.0)

    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(1.8)

    enhancer = ImageEnhance.Brightness(image)
    image = enhancer.enhance(1.4)

    return image

def correct_image_orientation(image):
    try:
        for orientation in ExifTags.TAGS.keys():
            if ExifTags.TAGS[orientation] == 'Orientation':
                break

        exif = dict(image._getexif().items())

        if exif[orientation] == 3:
            image = image.rotate(180, expand=True)
        elif exif[orientation] == 6:
            image = image.rotate(270, expand=True)
        elif exif[orientation] == 8:
            image = image.rotate(90, expand=True)
    except (AttributeError, KeyError, IndexError):
        pass

    return image

def resize_image(image, scale):
    width, height = image.size
    return image.resize((int(width * scale), int(height * scale)), Image.LANCZOS)
