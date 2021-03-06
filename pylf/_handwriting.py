""" The core module """
import multiprocessing
import random
import PIL.Image
import PIL.ImageDraw


_DEFAULT_COLOR = (0, 0, 0)
_DEFAULT_WORD_SPACING = 0
_DEFAULT_IS_HALF_CHARS = lambda c: False
# Chinese, English and other end chars
_DEFAULT_IS_END_CHARS = lambda c: c in ("，。》、？；：’”】｝、！％）" + ",.>?;:]}!%)" + "′″℃℉")


def handwrite(text, template: dict, anti_aliasing: bool=True, worker: int=0) -> list:
    """
    Simulating Chinese handwriting through introducing numerous randomness in the process.
    The module uses a Cartesian pixel coordinate system, with (0,0) in the upper left corner as same as Pillow Module.
    Note that, the module is built for simulating Chinese handwriting instead of English(or other languages')
    handwriting. Though injecting pieces of exotic language generally may not effect the overall performance, you should
    NOT count on it has a great performance in the domain of non-Chinese handwriting.

    :param text: a char iterable

    :param template: a dict containing the settings of the template
        The dict should contain below settings:
        'background': <Image>
            An Image object used as the background
        'box': (<int>, <int>, <int>, <int>)
            A bounding box as a 4-tuple defining the left, upper, right, and lower pixel coordinate
            NOTE: The bounding area should be in the 'background'. In other words, it should be in (0, 0,
            background.width, background.height).
            NOTE: The function do NOT guarantee the drawn texts will completely in the 'box' due to the used randomness.
        'font': <FreeTypeFont>
            NOTE: the size of the FreeTypeFont Object means nothing in the function.
        'font_size': <int>
            The average font size in pixel
        'font_size_sigma': <float>
            The sigma of the gauss distribution of the font size
        'line_spacing': <int>
            The average line spacing in pixel
        'line_spacing_sigma': <float>
            The sigma of the gauss distribution of the line spacing
        'word_spacing': <int>
            The average gap between two adjacent char in pixel
            default: 0
        'word_spacing_sigma': <float>
            The sigma of the gauss distribution of the word spacing

        Optional:
        'color': (<int>, <int>, <int>)
            The color of font in RGB. These values should be within [0, 255].
            default: (0, 0, 0)
        'is_half_char': <callable>
            A function judges whether or not a char only take up half of its original width
            The function must take a char parameter and return a boolean value.
            The feature is designed for some of Chinese punctuations that only take up the left half of their
            space (e.g. '，', '。').
        'is_end_char': <callable>
            A function judges whether or not a char can NOT be in the beginning of the lines (e.g. '，' , '。', '》')
            The function must take a char parameter and return a boolean value.

        Advanced:
        If you do NOT fully understand the algorithm, please leave these value default.
        'x_amplitude': <float>
            default: 0.06 * font_size
        'y_amplitude': <float>
            default: 0.06 * font_size
        'x_wavelength': <float>
            default: 2 * font_size
        'y_wavelength': <float>
            default: 2 * font_size
        'x_lambd': <float>
            default: 1 / font_size
        'y_lambd': <float>
            default: 1 / font_size
    
    :param anti_aliasing: whether or not turn on the anti-aliasing
        It will do the anti-aliasing with using 4X SSAA. Generally, to turn off this anti-aliasing option would
        significantly reduce the computational cost.
        default: True

    :param worker: the number of worker
        if worker <= 0, the actual amount of worker would be multiprocessing.cpu_count() + worker.
        default: 0 (use all available CPU in the computer)

    :return: a list of drawn images
    """
    template = dict(template)
    if 'color' not in template:
        template['color'] = _DEFAULT_COLOR
    if 'word_spacing' not in template:
        template['word_spacing'] = _DEFAULT_WORD_SPACING
    if 'is_half_char' not in template:
        template['is_half_char'] = _DEFAULT_IS_HALF_CHARS
    if 'is_end_char' not in template:
        template['is_end_char'] = _DEFAULT_IS_END_CHARS

    font_size = template['font_size']
    if 'x_amplitude' not in template:
        template['x_amplitude'] = 0.06 * font_size
    if 'y_amplitude' not in template:
        template['y_amplitude'] = 0.06 * font_size
    if 'x_wavelength' not in template:
        template['x_wavelength'] = 2 * font_size
    if 'y_wavelength' not in template:
        template['y_wavelength'] = 2 * font_size
    if 'x_lambd' not in template:
        template['x_lambd'] = 1 / font_size
    if 'y_lambd' not in template:
        template['y_lambd'] = 1 / font_size

    worker = worker if worker > 0 else multiprocessing.cpu_count() + worker
    return _handwrite(text, template, anti_aliasing, worker)


def _handwrite(text, template, anti_aliasing, worker):
    images = _draw_text(
        text=text,
        size=tuple(2 * i for i in template['background'].size) if anti_aliasing else template['background'].size,
        box=tuple(2 * i for i in template['box']) if anti_aliasing else template['box'],
        color=template['color'],
        font=template['font'],
        font_size=template['font_size'] * 2 if anti_aliasing else template['font_size'],
        font_size_sigma=template['font_size_sigma'] * 2 if anti_aliasing else template['font_size_sigma'],
        line_spacing=template['line_spacing'] * 2 if anti_aliasing else template['line_spacing'],
        line_spacing_sigma=template['line_spacing_sigma'] * 2 if anti_aliasing else template['line_spacing_sigma'],
        word_spacing=template['word_spacing'] * 2 if anti_aliasing else template['word_spacing'],
        word_spacing_sigma=template['word_spacing_sigma'] * 2 if anti_aliasing else template['word_spacing_sigma'],
        is_end_char=template['is_end_char'],
        is_half_char=template['is_half_char']
    )
    if not images:
        return images
    render = _RenderMaker(anti_aliasing, **template)
    with multiprocessing.Pool(min(worker, len(images))) as pool:
        images = pool.map(render, images)
    return images


def _draw_text(
        text,
        size,
        box,
        color,
        font,
        font_size,
        font_size_sigma,
        line_spacing,
        line_spacing_sigma,
        word_spacing,
        word_spacing_sigma,
        is_end_char,
        is_half_char
):
    """
    Draw the text randomly in blank images
    :return: a list of drawn images
    :raise: ValueError
    """
    if not box[3] - box[1] > font_size:
        raise ValueError('(box[3] - box[1]) must be greater than font_size.')
    if not box[2] - box[0] > font_size:
        raise ValueError('(box[2] - box[0]) must be greater than font_size.')

    left, upper, right, lower = box
    chars = iter(text)
    images = []
    try:
        char = next(chars)
        while True:
            image = PIL.Image.new('RGBA', size, color=(0, 0, 0, 0))
            draw = PIL.ImageDraw.Draw(image)
            y = upper
            try:
                while y < lower - font_size:
                    x = left
                    while True:
                        if char == '\n':
                            char = next(chars)
                            break
                        if x >= right - font_size and not is_end_char(char):
                            break
                        actual_font_size = int(random.gauss(font_size, font_size_sigma))
                        xy = x, int(random.gauss(y, line_spacing_sigma))
                        font = font.font_variant(size=actual_font_size)
                        draw.text(xy, char, fill=(*color, 255), font=font)
                        font_width = font.getsize(char)[0]
                        x_step = word_spacing + font_width * (1 / 2 if is_half_char(char) else 1)
                        x += int(random.gauss(x_step, word_spacing_sigma))
                        char = next(chars)
                    y += line_spacing
                images.append(image)
            except StopIteration:
                images.append(image)
                raise StopIteration()
    except StopIteration:
        return images


class _RenderMaker:
    """
    The maker of the function-like object rendering the foreground that was drawn text and returning finished image
    """

    def __init__(
            self,
            anti_aliasing,
            background,
            x_amplitude,
            y_amplitude,
            x_wavelength,
            y_wavelength,
            x_lambd,
            y_lambd,
            **kwargs
    ):
        self.__anti_aliasing = anti_aliasing
        self.__background = background
        self.__x_amplitude = x_amplitude * 2 if anti_aliasing else x_amplitude
        self.__y_amplitude = y_amplitude * 2 if anti_aliasing else y_amplitude
        self.__x_wavelength = x_wavelength * 2 if anti_aliasing else x_wavelength
        self.__y_wavelength = y_wavelength * 2 if anti_aliasing else y_wavelength
        self.__x_lambd = x_lambd / 2 if anti_aliasing else x_lambd
        self.__y_lambd = y_lambd / 2 if anti_aliasing else y_lambd
        self.__random = random.Random()

    def __call__(self, image):
        self.__random.seed()
        image = self.__perturb(image)
        if self.__anti_aliasing:
            image = self.__downsample(image)
        return self.__merge(image)

    def __perturb(self, image):
        """ 'Perturb' the image and generally make the glyphs from same chars, if any, seem different """
        from math import sin, pi
        height = image.height
        width = image.width
        px = image.load()
        start = 0
        for x in range(width):
            if x >= start + self.__x_wavelength:
                start = x + self.__random.expovariate(self.__x_lambd)
            if x <= start:
                continue
            offset = int(self.__x_amplitude * (sin(2 * pi * (x - start) / self.__x_wavelength - pi / 2) + 1))
            for y in range(height - offset):
                px[x, y] = px[x, y + offset]
            for y in range(height - offset, height):
                px[x, y] = (0, 0, 0, 0)
        start = 0
        for y in range(height):
            if y >= start + self.__y_wavelength:
                start = y + self.__random.expovariate(self.__y_lambd)
            if y <= start:
                continue
            offset = int(self.__y_amplitude * (sin(2 * pi * (y - start) / self.__y_wavelength - pi / 2) + 1))
            for x in range(width - offset):
                px[x, y] = px[x + offset, y]
            for x in range(width - offset, width):
                px[x, y] = (0, 0, 0, 0)
        return image

    @staticmethod
    def __downsample(image):
        """ Downsample the image for 4X SSAA """
        width, height = image.size[0] // 2, image.size[1] // 2
        sampled_image = PIL.Image.new('RGBA', (width, height), color=(0, 0, 0, 0))
        spx, px = sampled_image.load(), image.load()
        for x in range(width):
            for y in range(height):
                spx[x, y] = (tuple(sum(i) // 4 for i in zip(px[2 * x, 2 * y], px[2 * x + 1, 2 * y],
                                                            px[2 * x, 2 * y + 1], px[2 * x + 1, 2 * y + 1])))
        return sampled_image

    def __merge(self, image):
        """ Merge the foreground and the background image """
        self.__background.paste(image, mask=image)
        return self.__background
