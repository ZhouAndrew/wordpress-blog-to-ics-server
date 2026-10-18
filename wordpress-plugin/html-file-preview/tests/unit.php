<?php
// Standalone contract tests with WordPress function doubles.
error_reporting( E_ALL );
define( 'ABSPATH', '/test/' );
$GLOBALS['hfp_url'] = array( 12 => 'https://andrew.local/wp-content/uploads/report.html' );
$GLOBALS['hfp_mime'] = array( 12 => 'text/html' );
$GLOBALS['hfp_filters'] = array();
function add_filter( $hook, $callback ) { $GLOBALS['hfp_filters'][ $hook ] = $callback; }
function add_action() {}
function absint( $v ) { return abs( (int) $v ); }
function wp_get_attachment_url( $id ) { return $GLOBALS['hfp_url'][ $id ] ?? false; }
function get_post_mime_type( $id ) { return $GLOBALS['hfp_mime'][ $id ] ?? false; }
function wp_parse_url( $v ) { return parse_url( $v ); }
function home_url( $path = '' ) { return 'https://andrew.local/' . ltrim( $path, '/' ); }
function trailingslashit( $v ) { return rtrim( $v, '/' ) . '/'; }
function esc_url_raw( $v, $allowed = array() ) { return $v; }
function esc_url( $v ) { return htmlspecialchars( $v, ENT_QUOTES, 'UTF-8' ); }
function esc_html( $v ) { return htmlspecialchars( $v, ENT_QUOTES, 'UTF-8' ); }
function esc_attr( $v ) { return htmlspecialchars( $v, ENT_QUOTES, 'UTF-8' ); }
function __( $v, $domain ) { return $v; }
require dirname( __DIR__ ) . '/html-file-preview.php';

function check( $condition, $name ) {
    if ( ! $condition ) {
        fwrite( STDERR, "FAIL: $name\n" );
        exit( 1 );
    }
    echo "PASS: $name\n";
}

check( HFP_VERSION === '0.2.2-beta.1', 'version upgraded' );
$args = hfp_register_file_attributes( array( 'attributes' => array( 'href' => array( 'type' => 'string' ) ) ), 'core/file' );
check( isset( $args['attributes']['href'] ) && $args['attributes']['hfpShowPreview']['default'] === false &&
    $args['attributes']['hfpPreviewHeight']['default'] === 600, 'server-side attributes registered without replacing core attrs' );
check( hfp_register_file_attributes( array( 'attributes' => array() ), 'core/paragraph' ) === array( 'attributes' => array() ), 'unrelated blocks unchanged' );
check( hfp_preview_height( array() ) === 600, 'default height 600 pixels' );
check( hfp_preview_height( array( 'hfpPreviewHeight' => 800 ) ) === 800, 'custom height persisted' );
check( hfp_preview_height( array( 'hfpPreviewHeight' => -2 ) ) === 100, 'low height clamped' );
check( hfp_preview_height( array( 'hfpPreviewHeight' => 7000 ) ) === 2000, 'high height clamped' );
check( hfp_preview_height( array( 'hfpPreviewHeight' => 'broken' ) ) === 600, 'invalid height falls back safely' );

$core = '<div class="wp-block-file"><a href="/wp-content/uploads/report.html">report</a><a class="wp-block-file__button" download>Download</a></div>';
$block = array( 'attrs' => array( 'href' => '/wp-content/uploads/report.html' ) );
$out = hfp_render_file_block( $core, $block );
check( $out === $core, 'existing HTML blocks do not get forced iframes' );
check( hfp_render_file_block( $core, array( 'attrs' => array( 'id' => 12 ) ) ) === $core, 'HTML attachment ID does not auto-preview' );
check( hfp_render_file_block( $core, array( 'attrs' => array( 'href' => '/uploads/a.html', 'hfpShowPreview' => false ) ) ) === $core, 'explicit off suppresses iframe' );
$enabled = array( 'attrs' => array( 'href' => '/uploads/a.html', 'hfpShowPreview' => true ) );
$out = hfp_render_file_block( $core, $enabled );
check( substr_count( $out, '<iframe ' ) === 1, 'explicit on produces exactly one iframe' );
check( strpos( $out, 'style="height:600px"' ) !== false, 'enabled default height 600' );
check( strpos( $out, 'sandbox="allow-scripts"' ) !== false && strpos( $out, 'allow-same-origin' ) === false, 'sandbox keeps opaque origin' );
check( strpos( $out, 'download>Download</a>' ) !== false, 'native download preserved' );
check( strpos( $out, '</iframe></div></div>' ) !== false, 'preview nested inside native wrapper' );
check( hfp_render_file_block( $out, $enabled ) === $out, 'no duplicate iframe' );
$custom = hfp_render_file_block( $core, array( 'attrs' => array( 'href' => '/uploads/file.html', 'hfpShowPreview' => true, 'hfpPreviewHeight' => 990 ) ) );
check( strpos( $custom, 'height:990px' ) !== false, 'enabled custom height renders on frontend' );
check( hfp_render_file_block( $core, array( 'attrs' => array( 'id' => 12, 'hfpShowPreview' => true ) ) ) !== $core, 'HTML attachment ID with explicit on works' );
check( hfp_render_file_block( $core, array( 'attrs' => array( 'href' => '/uploads/file.pdf', 'displayPreview' => true ) ) ) === $core, 'PDF + native PDF setting untouched' );
check( hfp_render_file_block( $core, array( 'attrs' => array( 'href' => '/uploads/file.ics' ) ) ) === $core, 'ICS untouched' );
check( hfp_preview_url( array( 'href' => 'https://evil.example/f.html' ) ) === '', 'external URL blocked' );
check( hfp_preview_url( array( 'href' => '//andrew.local/f.html' ) ) === '', 'protocol-relative URL blocked' );
check( hfp_preview_url( array( 'href' => 'javascript:/f.html' ) ) === '', 'unsafe scheme blocked' );
check( hfp_preview_url( array( 'href' => 'http://andrew.local/f.html' ) ) === '', 'mixed scheme blocked' );
check( hfp_preview_url( array( 'href' => 'https://user:password@andrew.local/file.html' ) ) === '', 'credentialed URL blocked' );
check( hfp_preview_url( array( 'href' => '/uploads/f.HTM?foo=1' ) ) === 'https://andrew.local/uploads/f.HTM?foo=1', 'HTM and query supported' );
check( hfp_preview_url( array( 'textLinkHref' => '/uploads/case.HTML' ) ) === 'https://andrew.local/uploads/case.HTML', 'alternative File link fallback' );
check( hfp_preview_url( array( 'href' => '/attachments/none/', 'textLinkHref' => '/uploads/case.html' ) ) === 'https://andrew.local/uploads/case.html', 'attachment page link uses alternate media link' );
check( hfp_preview_url( array( 'href' => 'uploads/f.html' ) ) === 'https://andrew.local/uploads/f.html', 'relative URL resolves to WordPress home' );
check( hfp_preview_url( array( 'href' => '/uploads/report.html', 'id' => 12 ) ) === $GLOBALS['hfp_url'][12], 'ID resolves media direct URL' );
check( hfp_preview_url( array( 'href' => '/uploads/report.php', 'id' => 12 ) ) === $GLOBALS['hfp_url'][12], 'attachment page link resolves HTML' );
check( hfp_render_file_block( $core, array() ) === $core, 'missing attributes untouched' );
$stats = array( 'file_blocks' => 0, 'html_file_blocks' => 0, 'custom_html_blocks' => 0, 'embed_blocks' => 0 );
hfp_diagnose_block( array( 'blockName' => 'core/group', 'innerBlocks' => array(
    array( 'blockName' => 'core/file', 'attrs' => array( 'href' => '/uploads/inside.html' ) ),
    array( 'blockName' => 'core/file', 'attrs' => array( 'href' => '/uploads/inside.pdf' ) ),
    array( 'blockName' => 'core/html' ),
) ), $stats );
check( $stats['file_blocks'] === 2 && $stats['html_file_blocks'] === 1 && $stats['custom_html_blocks'] === 1, 'read-only diagnostics counts nested block types' );
echo "All PHP unit tests passed.\n";
