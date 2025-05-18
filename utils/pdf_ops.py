import pymupdf

def extract_links_from_pdf(fileobj):
    all_links = []

    doc = pymupdf.open(fileobj)
    for page in doc:
        links = [ link.get('file', None) for link in page.get_links() ]
        all_links.extend([ link for link in links if link is not None ])

    return all_links

def convert_to_image_pdf(file_bytes):
    outdoc = pymupdf.open()

    doc = pymupdf.open(stream=file_bytes, filetype='pdf')
    
    for page in doc:

        img_bytes = page.get_pixmap(alpha=False, dpi=300)\
                        .tobytes(output='jpg', jpg_quality=10)

        img           = pymupdf.open(stream=img_bytes, filetype='jpg')
        img_pdf_bytes = img.convert_to_pdf()
        img_rect      = img[0].rect

        img.close()

        img_pdf = pymupdf.open(stream=img_pdf_bytes, filetype='pdf')

        page = outdoc.new_page(width  = img_rect.width,
                               height = img_rect.height)

        page.show_pdf_page(img_rect, img_pdf, 0)

    return outdoc.tobytes()

def convert_to_image_pdf_file(inp_file, outp_file):
    with open(inp_file, 'rb') as f:
        file_bytes = f.read()

    pdf_bytes = convert_to_image_pdf(file_bytes)

    with open(outp_file, 'wb') as f:
        f.write(pdf_bytes)


if __name__ == '__main__':
    import sys
    from pathlib import Path
    pdf_bytes = convert_to_image_pdf(Path(sys.argv[1]).read_bytes())
    Path(sys.argv[2]).write_bytes(pdf_bytes)

