<?php
// Run with wp eval-file wordpress-plugin/html-file-preview/tests/wordpress-integration.php
if ( ! defined( 'ABSPATH' ) || ! function_exists( 'do_blocks' ) ) {
    fwrite( STDERR, "This test must run inside WordPress.\n" );
    exit( 1 );
}
function hfp_wp_assert( $okay, $message ) {
    if ( ! $okay ) {
        WP_CLI::error( $message );
    }
    WP_CLI::log( 'PASS: ' . $message );
}
hfp_wp_assert( function_exists( 'hfp_preview_url' ), 'plugin loaded' );
hfp_wp_assert( WP_Block_Type_Registry::get_instance()->is_registered( 'core/file' ), 'core/file registered' );
$url = home_url( '/wp-content/uploads/fixture.html' );
$inner = '<div class="wp-block-file"><a href="' . esc_url( $url ) . '">Fixture</a>' .
    '<a href="' . esc_url( $url ) . '" class="wp-block-file__button" download>Download</a></div>';
$block = static function ( $attributes ) use ( $inner ) {
    return '<!-- wp:file ' . wp_json_encode( $attributes ) . ' -->' . $inner . '<!-- /wp:file -->';
};
$off = do_blocks( $block( array( 'href' => $url ) ) );
hfp_wp_assert( false === strpos( $off, 'data-hfp-preview' ), 'existing HTML File block defaults to no preview' );
$on = do_blocks( $block( array( 'href' => $url, 'hfpShowPreview' => true, 'hfpPreviewHeight' => 720 ) ) );
hfp_wp_assert( 1 === substr_count( $on, '<iframe ' ), 'explicit opt-in creates one iframe' );
hfp_wp_assert( false !== strpos( $on, 'height:720px' ) || false !== strpos( $on, 'height="720"' ), 'per-block height rendered' );
hfp_wp_assert( false !== strpos( $on, 'download>Download</a>' ), 'native download preserved' );
hfp_wp_assert( false !== strpos( $on, 'sandbox="allow-scripts"' ), 'sandbox stays restricted' );
$disabled = do_blocks( $block( array( 'href' => $url, 'hfpShowPreview' => false ) ) );
hfp_wp_assert( false === strpos( $disabled, 'data-hfp-preview' ), 'explicit off prevents iframe' );
$pdf = do_blocks( $block( array( 'href' => str_replace( '.html', '.pdf', $url ) ) ) );
hfp_wp_assert( false === strpos( $pdf, 'data-hfp-preview' ), 'PDF unaffected' );
do_action( 'enqueue_block_editor_assets' );
hfp_wp_assert( wp_script_is( 'hfp-editor', 'enqueued' ), 'editor script enqueued' );
hfp_wp_assert( wp_style_is( 'hfp-preview', 'enqueued' ), 'preview stylesheet enqueued' );
WP_CLI::success( 'HTML File Preview real WordPress integration checks passed.' );
