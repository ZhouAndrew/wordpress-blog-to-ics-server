<?php
// Standalone contract tests with minimal WordPress function doubles.
error_reporting( E_ALL );
define( 'ABSPATH', '/test/' );
$GLOBALS['hfp_url']  = array( 12 => 'https://andrew.local/wp-content/uploads/report.html' );
$GLOBALS['hfp_mime'] = array( 12 => 'text/html' );
function add_filter() {}
function add_action() {}
function absint( $v ) { return abs( (int) $v ); }
function wp_get_attachment_url( $id ) { return $GLOBALS['hfp_url'][ $id ] ?? false; }
function get_post_mime_type( $id ) { return $GLOBALS['hfp_mime'][ $id ] ?? false; }
function wp_parse_url( $v ) { return parse_url( $v ); }
function home_url( $path = '' ) { return 'https://andrew.local/' . ltrim( $path, '/' ); }
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

$core = '<div class="wp-block-file"><a href="/wp-content/uploads/report.html">report</a><a class="wp-block-file__button" download>Download</a></div>';
$block = array( 'attrs' => array( 'href' => '/wp-content/uploads/report.html' ) );
$out = hfp_render_file_block( $core, $block );
check( substr_count( $out, '<iframe ' ) === 1, 'HTML gets one iframe' );
check( strpos( $out, 'sandbox="allow-scripts"' ) !== false && strpos( $out, 'allow-same-origin' ) === false, 'iframe sandbox avoids same origin' );
check( strpos( $out, 'download>Download</a>' ) !== false, 'native download preserved' );
check( strpos( $out, '</iframe></div></div>' ) !== false, 'iframe nested in native wrapper' );
check( hfp_render_file_block( $out, $block ) === $out, 'preview is not duplicated' );
check( hfp_render_file_block( $core, array( 'attrs' => array( 'href' => '/uploads/file.pdf' ) ) ) === $core, 'PDF untouched' );
check( hfp_render_file_block( $core, array( 'attrs' => array( 'href' => '/uploads/file.ics' ) ) ) === $core, 'ICS untouched' );
check( hfp_preview_url( array( 'href' => 'https://evil.example/f.html' ) ) === '', 'external URL blocked' );
check( hfp_preview_url( array( 'href' => '//andrew.local/f.html' ) ) === '', 'protocol relative URL blocked' );
check( hfp_preview_url( array( 'href' => 'javascript:/f.html' ) ) === '', 'unsafe scheme blocked' );
check( hfp_preview_url( array( 'href' => 'http://andrew.local/f.html' ) ) === '', 'mixed scheme blocked' );
check( hfp_preview_url( array( 'href' => '/uploads/f.HTM?foo=1' ) ) !== '', 'HTM and query supported' );
check( hfp_preview_url( array( 'href' => '/uploads/report.html', 'id' => 12 ) ) === $GLOBALS['hfp_url'][12], 'attachment ID resolves media direct URL' );
check( hfp_preview_url( array( 'href' => '/uploads/report.php', 'id' => 12 ) ) === $GLOBALS['hfp_url'][12], 'attachment page link resolves HTML' );
check( hfp_render_file_block( $core, array() ) === $core, 'missing attributes untouched' );
echo "All PHP unit tests passed.\n";
