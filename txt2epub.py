import os
import re
import zipfile
from datetime import datetime
from textwrap import dedent

class EpubGenerator:
    def __init__(self, txt_path, output_path):
        self.txt_path = txt_path
        self.output_path = output_path
        self.books = []
        self.current_volume = None
        self.current_chapter = None
        self.manifest = []
        self.spine = []
        self.nav_points = []
        self.metadata = {
            'title': '默认标题',
            'author': '默认作者',
            'description': ''
        }

    def parse_txt(self):
        with open(self.txt_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        volume_pattern = re.compile(r'^\[卷名\] (.+)$')
        metadata_section = False

        for i, line in enumerate(lines):
            line = line.rstrip('\n')
            
            # 解析元数据
            if line == '━━━━━━━━━':
                metadata_section = True
                continue
                
            if metadata_section:
                if line.startswith('「书名：'):
                    self.metadata['title'] = line[4:-1]
                elif line.startswith('「作者：'):
                    self.metadata['author'] = line[4:-1]
                elif line.startswith('「书籍简介：'):
                    self.metadata['description'] = lines[i+1].strip()
                    metadata_section = False
                continue

            # 解析卷和章节
            if volume_match := volume_pattern.match(line):
                self.current_volume = {
                    'title': volume_match.group(1),
                    'chapters': []
                }
                self.books.append(self.current_volume)
                self.current_chapter = None
            elif self.current_volume is not None:
                stripped_line = line.strip()
                if not line.startswith((' ', '　')) and stripped_line != '':
                    self.current_chapter = {
                        'title': stripped_line,
                        'content': []
                    }
                    self.current_volume['chapters'].append(self.current_chapter)
                elif self.current_chapter is not None:
                    self.current_chapter['content'].append(line)

    def create_epub_structure(self):
        os.makedirs('epub/OEBPS', exist_ok=True)
        os.makedirs('epub/META-INF', exist_ok=True)

        with open('epub/mimetype', 'w', encoding='utf-8') as f:
            f.write('application/epub+zip')

        container_xml = dedent('''\
        <?xml version="1.0"?>
        <container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
          <rootfiles>
            <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
          </rootfiles>
        </container>
        ''')
        with open('epub/META-INF/container.xml', 'w', encoding='utf-8') as f:
            f.write(container_xml)

    def process_images(self, text):
        text = text.replace('：', ':')
        img_pattern = re.compile(r'\[img=(\d+)[，, ]*(\d+)\](.*?)\[/img\]', re.IGNORECASE)
        return img_pattern.sub(r'<img src="\3" width="\1" height="\2"/>', text)

    def generate_chapters(self):
        for vol_idx, volume in enumerate(self.books, start=1):
            for chap_idx, chapter in enumerate(volume['chapters'], start=1):
                filename = f'vol{vol_idx}_chap{chap_idx}.xhtml'
                self.manifest.append({
                    'id': filename.split('.')[0],
                    'href': filename,
                    'media-type': 'application/xhtml+xml'
                })
                self.spine.append({'idref': filename.split('.')[0]})

                content = []
                for para in chapter['content']:
                    if para.strip() == '':
                        content.append('<p>&#160;</p>')
                    else:
                        processed = self.process_images(para)
                        content.append(f'<p>{processed}</p>')

                xhtml = dedent(f'''\
                <?xml version="1.0" encoding="utf-8"?>
                <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"
                  "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
                <html xmlns="http://www.w3.org/1999/xhtml">
                <head>
                  <title>{chapter["title"]}</title>
                </head>
                <body>
                  <h2>{chapter["title"]}</h2>
                  {"".join(content)}
                </body>
                </html>
                ''')

                with open(f'epub/OEBPS/{filename}', 'w', encoding='utf-8') as f:
                    f.write(xhtml)

    def generate_toc(self):
        toc_xml = dedent('''\
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" 
          "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">
        <ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
          <head>
            <meta name="dtb:uid" content="urn:uuid:12345"/>
            <meta name="dtb:depth" content="2"/>
            <meta name="dtb:totalPageCount" content="0"/>
            <meta name="dtb:maxPageNumber" content="0"/>
          </head>
          <docTitle><text>{self.metadata['title']}</text></docTitle>
          <navMap>
        ''').format(self=self)
        
        nav_id = 1
        for vol_idx, volume in enumerate(self.books, start=1):
            toc_xml += f'''
            <navPoint id="nav{nav_id}" playOrder="{nav_id}">
              <navLabel><text>{volume["title"]}</text></navLabel>
              <content src="vol{vol_idx}_chap1.xhtml"/>'''
            nav_id +=1
            
            for chap_idx, chapter in enumerate(volume['chapters'], start=1):
                filename = f'vol{vol_idx}_chap{chap_idx}.xhtml'
                toc_xml += f'''
                <navPoint id="nav{nav_id}" playOrder="{nav_id}">
                  <navLabel><text>{chapter["title"]}</text></navLabel>
                  <content src="{filename}"/>
                </navPoint>'''
                nav_id +=1
            
            toc_xml += '</navPoint>'
        
        toc_xml += '</navMap></ncx>'
        
        with open('epub/OEBPS/toc.ncx', 'w', encoding='utf-8') as f:
            f.write(toc_xml)

    def generate_content_opf(self):
        manifest_items = '\n'.join(
            f'<item id="{item["id"]}" href="{item["href"]}" media-type="{item["media-type"]}"/>'
            for item in self.manifest
        )
        spine_items = '\n'.join(
            f'<itemref idref="{item["idref"]}"/>' 
            for item in self.spine
        )

        content_opf = dedent(f'''\
        <?xml version="1.0" encoding="utf-8"?>
        <package xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookId" version="2.0">
          <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
            <dc:identifier id="BookId">urn:uuid:12345</dc:identifier>
            <dc:title>{self.metadata['title']}</dc:title>
            <dc:language>zh-CN</dc:language>
            <dc:creator>{self.metadata['author']}</dc:creator>
            <dc:date>{datetime.now().strftime("%Y-%m-%d")}</dc:date>
            <dc:description>{self.metadata['description']}</dc:description>
          </metadata>
          <manifest>
            <item id="toc" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
            {manifest_items}
          </manifest>
          <spine toc="toc">
            {spine_items}
          </spine>
        </package>
        ''')

        with open('epub/OEBPS/content.opf', 'w', encoding='utf-8') as f:
            f.write(content_opf)

    def zip_epub(self):
        with zipfile.ZipFile(self.output_path, 'w') as zf:
            zf.write('epub/mimetype', 'mimetype', compress_type=zipfile.ZIP_STORED)
            for root, _, files in os.walk('epub'):
                for file in files:
                    if file == 'mimetype':
                        continue
                    path = os.path.join(root, file)
                    arcname = os.path.relpath(path, 'epub')
                    zf.write(path, arcname)

    def generate(self):
        self.parse_txt()
        self.create_epub_structure()
        self.generate_chapters()
        self.generate_toc()
        self.generate_content_opf()
        self.zip_epub()

if __name__ == '__main__':
    generator = EpubGenerator('input.txt', 'output.epub')
    generator.generate()
    print("EPUB生成完成！")
