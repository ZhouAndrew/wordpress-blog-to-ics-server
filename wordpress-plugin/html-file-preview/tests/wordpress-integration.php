<?php
// Run under: wp eval-file wordpress-plugin/html-file-preview/tests/wordpress-integration.php
if ( ! defined( 'ABSPATH' ) || ! function_exists( 'do_blocks' ) ) {
    fwrite( STDERR, "This test must be run in a real WordPress installation.\n" );
    exit( 1 );
}
function hfp_wp_assert( $okay, $message ) {
    if ( ! $okay ) {
        WP_CLI::error( $message );
    }
    WP_CLI::log( 'PASS: ' . $message );
}
hfp_wp_assert( function_exists( 'hfp_preview_url' ), 'plugin loaded and activated' );
hfp_wp_assert( WP_Block_Type_Registry::get_instance()->is_registered( 'core/file' ), 'native File block exists' );
$uri  = home_url( '/wp-content/uploads/fixture.html' );
$html = '<!-- wp:file {"href":"' . $uri . '"} -->' .
    '<div class="wp-block-file"><a href="' . $uri . '">Fixture</a>' .
    '<a href="' . $uri . '" class="wp-block-file__button" download>Download</a></div>' .
    '<!-- /wp:file -->';
$out = do_blocks( $html );
hfp_wp_assert( substr_count( $out, '<iframe ' ) === 1, 'actual Gutenberg rendering adds one HTML iframe' );
hfp_wp_assert( strpos( $out, 'data-hfp-preview' ) !== false, 'preview markup inserted' );
hfp_wp_assert( strpos( $out, 'download>Download</a>' ) !== false, 'original native download stays' );
hfp_wp_assert( strpos( $out, 'sandbox="allow-scripts"' ) !== false, 'real WordPress render has sandbox' );

$pdf = str_replace( 'fixture.html', 'fixture.pdf', $html );
$nonhtml = do_blocks( $pdf );
hfp_wp_assert( strpos( $nonhtml, 'data-hfp-preview' ) === false, 'actual PDF block unchanged' );

$other = '<!-- wp:paragraph --><p>Unrelated content</p><!-- /wp:paragraph -->';
hfp_wp_assert( strpos( do_blocks( $other ), 'data-hfp-preview' ) === false, 'unrelated Gutenberg blocks unchanged' );

do_action( 'enqueue_block_editor_assets' );
hfp_wp_assert( wp_script_is( 'hfp-editor', 'enqueued' ), 'editor JavaScript enqueued' );
hfp_wp_assert( wp_style_is( 'hfp-preview', 'enqueued' ), 'editor stylesheet enqueued' );
WP_CLI::success( 'All real WordPress integration tests passed.' );
