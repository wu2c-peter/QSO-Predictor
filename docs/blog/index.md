---
layout: page
title: Blog
permalink: /blog/
description: >-
  Stories from the operating position — real QSOs reconstructed from the
  data, feature deep-dives, and notes from building QSO Predictor.
---

Stories from the operating position: real QSOs told through the data that
QSO Predictor and WSJT-X leave behind, plus occasional notes from building
the app.

{% for post in site.posts %}
<article style="margin-bottom: 1.5em;">
  <h2 style="margin-bottom: 0.1em;"><a href="{{ post.url | relative_url }}">{{ post.title | escape }}</a></h2>
  <time datetime="{{ post.date | date_to_xmlschema }}" style="font-size: 0.85em; color: #828282;">{{ post.date | date: "%B %-d, %Y" }}</time>
  <p>{{ post.description | default: post.excerpt | strip_html | truncatewords: 45 }}</p>
</article>
{% endfor %}
