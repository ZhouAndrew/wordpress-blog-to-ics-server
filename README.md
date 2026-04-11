# wordpress-blog-to-ics-server
listen to wordpress server and convert post to ics server for user to subscripe 
The post might be like 
```
andrew@andrew:~$ wp post get 10213 --field=post_content --path=/var/www/html/wordpress
<!-- wp:paragraph -->
<p>07:45 Into the breakfast and bake the pizza</p>
<!-- /wp:paragraph -->

<!-- wp:paragraph -->
<p>07:48 Bake two pizzas for two minutes and 15 seconds</p>
<!-- /wp:paragraph -->

<!-- wp:paragraph -->
<p>08:13 I finished the dinner and have some snacks for sample the beef a small stick of beef</p>
<!-- /wp:paragraph -->

<!-- wp:paragraph -->
<p>8:30 I enabled Thunderbird on laptop</p>
<!-- /wp:paragraph -->

<!-- wp:file {"id":10221,"href":"https://andrew.local/wp-content/uploads/2026/04/ChatGPT-截图问题排查指南.html"} -->
<div class="wp-block-file"><a id="wp-block-file--media-5e0fe277-f1c3-467a-8141-900f64c0d798" href="https://andrew.local/wp-content/uploads/2026/04/ChatGPT-截图问题排查指南.html">ChatGPT-截图问题排查指南</a><a href="https://andrew.local/wp-content/uploads/2026/04/ChatGPT-截图问题排查指南.html" class="wp-block-file__button wp-element-button" download aria-describedby="wp-block-file--media-5e0fe277-f1c3-467a-8141-900f64c0d798">Download</a></div>
<!-- /wp:file -->

<!-- wp:paragraph -->
<p>9:56 I found the homework</p>
<!-- /wp:paragraph -->

<!-- wp:image {"id":10219,"sizeSlug":"large","linkDestination":"none"} -->
<figure class="wp-block-image size-large"><img src="https://andrew.local/wp-content/uploads/2026/04/8b45ac5741facb4310feb158a2ff5c88-1024x797.jpg" alt="" class="wp-image-10219"/><figcaption class="wp-element-caption">Oplus_16908288</figcaption></figure>
<!-- /wp:image -->

<!-- wp:file {"id":10224,"href":"https://andrew.local/wp-content/uploads/2026/04/ChatGPT-Transfer_Thunderbird_Data.html"} -->
<div class="wp-block-file"><a id="wp-block-file--media-c04713d4-7c58-4512-9cd9-6ffc577218eb" href="https://andrew.local/wp-content/uploads/2026/04/ChatGPT-Transfer_Thunderbird_Data.html">ChatGPT-Transfer_Thunderbird_Data</a><a href="https://andrew.local/wp-content/uploads/2026/04/ChatGPT-Transfer_Thunderbird_Data.html" class="wp-block-file__button wp-element-button" download aria-describedby="wp-block-file--media-c04713d4-7c58-4512-9cd9-6ffc577218eb">Download</a></div>
<!-- /wp:file -->

<!-- wp:paragraph -->
<p>10:11</p>
<!-- /wp:paragraph -->

<!-- wp:paragraph -->
<p></p>
<!-- /wp:paragraph -->
andrew@andrew:~$ ```
