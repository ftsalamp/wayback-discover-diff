from wayback_discover_diff import Discover
from bs4 import BeautifulSoup
from itertools import groupby


def test_newlines_start_end():
    response = '''<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN">
<html lang="en">
 <head>
  <title>HTML Parsing: newlines at the start and end of elements</title>
  <style type="text/css">
   p { color: green; }
   pre { background: red; }
  </style>
 </head>
 <body>
  <p>There should be no red below.</p>
  <!-- a newline immediately after a start tag or immediately before
  an end tag should be ignored, so the following element is empty. -->
  <pre>

</pre>
 </body>
</html>
'''
    lxml_result = Discover.calc_features(None, response)
    bs_result = calc_features(response)
    assert lxml_result == bs_result


def test_non_empty_comments():
    response = '''
    <!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN">
<title>Non-empty comments</title>
<style type="text/css">
 p { color: green; }
 span { color: red; }
</style>
<p>
 <!--> <span> <!-->
  This line should be green.
 <!--> </span> <!-->
</p>
    '''
    lxml_result = Discover.calc_features(None, response)
    bs_result = calc_features(response)
    assert lxml_result == bs_result


def test_broken_end_tags():
    response = '''
    <!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN">
<html>
 <head>
  <title>Parsing end tags with spaces (which are thus not end tags) </title>
 </head>
 <body>
  <script type="text/javacript">
    /* < /script> IF YOU SEE THIS THE TEST HAS FAILED <!-- */ // -->
  </script>
  <p>If this is the only line, this test has passed.</p>
 </body>
</html>
    '''
    lxml_result = Discover.calc_features(None, response)
    bs_result = calc_features(response)
    assert lxml_result == bs_result


def test_optional__end_tags():
    response = '''
    <!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN">
<html lang="en">
 <head>
  <title>HTML Parsing: Optional DT end tags</title>
  <style type="text/css">
   dt { color: red; }
   html > body > dl > dd > dl > dt { color: green; }
  </style>
 </head>
 <body>
  <dl>
   <dd>
    <dl>
     <dt> This text should be green and indented. </dt>
     <dt> This text should be green and indented. </dt>
    </dl>
   </dd>
  </dl>
  <dl>
   <dd>
    <dl>
     <dt> This text should be green and indented. <!-- implied end tag -->
     <dt> This text should be green and indented. </dt>
    </dl>
   </dd>
  </dl>
 </body>
</html>
'''
    lxml_result = Discover.calc_features(None, response)
    bs_result = calc_features(response)
    assert lxml_result == bs_result


def test_html():
    response = '''
    <!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN">
<html lang="en">
 <head>
  <title>HTML Parsing: DL</title>
  <style type="text/css">
   * { color: red; }
   html > body > dl > dd > dl > dd { color: green; }
  </style>
 </head>
 <body>
  <dl>
   <dd>
    <dl>
     <dd> This text should be green. </dd>
    </dl>
   </dd>
  </dl>
 </body>
</html>
'''
    lxml_result = Discover.calc_features(None, response)
    bs_result = calc_features(response)
    assert lxml_result == bs_result


def test_css_js():
    response = '''
    <!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN">
<html>
 <head>
  <title>Parsing style blocks correctly</title>
  <style type="text/css">/**/
   p { color: green; }
   &#x70; { color: yellow; background: red; }
   .test:after { content: '&#x46;&#x41;&#x49;&#x4c;'; }
  /**/</style>
 </head>
 <body>
  <p>This line should be green.</p>
  <div class="test">This line should end with a string of garbage: </div>
  <pre id="result">(The script part of this test failed for probably unrelated reasons.)</pre>
  <script type="text/javascript">
   var s1 = document.getElementsByTagName('style')[0].firstChild.data;
   var s2 = '/**/\n   p { color: green; }\n   &#x70; { color: yellow; background: red; }\n   .test:after { content: \'\&\#x46\;\&\#x4' + '1\;\&' + '\#x49\;\&\#x4c\;\'; }\n  /**/';
   var result = s1 == s2;
   document.getElementById('result').firstChild.data = result ? '' : 'The error is in the parser, which thought the <style> block contained:\n\n  <style ...>' + s1 + '<\/style>\n\nIt should have contained:\n\n  <style ...>' + s2 + '<\/style>';
  </script>
 </body>
</html>
'''
    lxml_result = Discover.calc_features(None, response)
    bs_result = calc_features(response)
    assert lxml_result == bs_result


def test_mixed_head_body():
    response = '''
    <!DOCTYPE HTML>
<html>
 <head>
  <title>Spaces</title>
 </head>
 <body>
  <p>The next five lines should be identical:</p>
  <pre>Hello</head>     World
Hello     World
Hello</body>     World
Hello     World
Hello</html>     World</pre>
 </body>
</html>
'''
    lxml_result = Discover.calc_features(None, response)
    bs_result = calc_features(response)
    assert lxml_result == bs_result


def calc_features(response):

    soup = BeautifulSoup(response, "lxml")

    # kill all script and style elements
    for script in soup(["script", "style"]):
        script.extract()  # rip it out

    # get text
    text = soup.get_text()
    # turn all characters to lowercase
    text = text.lower()
    # break into lines and remove leading and trailing space on each
    lines = (line.strip() for line in text.splitlines())
    # break multi-headlines into a line each
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    # drop blank lines
    text = '\n'.join(chunk for chunk in chunks if chunk)

    text = text.split()

    text = {k: sum(1 for _ in g) for k, g in groupby(sorted(text))}
    return text
