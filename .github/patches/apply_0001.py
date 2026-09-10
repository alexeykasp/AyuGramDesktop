#!/usr/bin/env python3
"""Apply lottie guard-exceptions patch (0001) adapted for AyuGram's lottie_wrap.h."""
import sys
import os

GUARD = '''
namespace {

// rlottie can throw (std::bad_alloc, std::out_of_range and friends) while
// parsing or interpolating a malformed animation. If that happens on a
// background (Qt Concurrent) thread it is fatal for the whole process, since
// nothing up the call chain is able to catch it. Guard the two entry points
// (load + render) so a broken sticker degrades to "doesn't play" instead of
// crashing the app for everyone who opens the same sticker/pack.
[[nodiscard]] std::unique_ptr<rlottie::Animation> SafeLoadFromData(
\t\tstd::string data,
\t\tstd::string key,
\t\tstd::string resourcePath,
\t\tbool cache,
\t\tconst std::vector<std::pair<std::uint32_t, std::uint32_t>> &colorReplacements,
\t\trlottie::FitzModifier fitzModifier) {
\ttry {
\t\treturn LoadAnimationFromData(
\t\t\tstd::move(data),
\t\t\tstd::move(key),
\t\t\tstd::move(resourcePath),
\t\t\tcache,
\t\t\tcolorReplacements,
\t\t\tfitzModifier);
\t} catch (const std::exception &e) {
\t\tLOG(("Lottie Error: Exception in loadFromData: %1"
\t\t\t).arg(QString::fromUtf8(e.what())));
\t} catch (...) {
\t\tLOG(("Lottie Error: Unknown exception in loadFromData."));
\t}
\treturn nullptr;
}

bool SafeRenderSync(
\t\tconst std::unique_ptr<rlottie::Animation> &animation,
\t\tsize_t frame,
\t\trlottie::Surface surface) {
\ttry {
\t\tanimation->renderSync(frame, std::move(surface));
\t\treturn true;
\t} catch (const std::exception &e) {
\t\tLOG(("Lottie Error: Exception in renderSync: %1"
\t\t\t).arg(QString::fromUtf8(e.what())));
\t} catch (...) {
\t\tLOG(("Lottie Error: Unknown exception in renderSync."));
\t}
\treturn false;
}

} // namespace
'''

OLD_LOAD = '''\tLoadAnimationFromData(
\t\tReadUtf8(Images::UnpackGzip(bytes)),
\t\tstd::string(),
\t\tstd::string(),
\t\tfalse)) {'''

NEW_LOAD = '''\tSafeLoadFromData(
\t\tReadUtf8(Images::UnpackGzip(bytes)),
\t\tstd::string(),
\t\tstd::string(),
\t\tfalse,
\t\t{},
\t\trlottie::FitzModifier::None)) {'''

OLD_RENDER = '''\t_rlottie->renderSync(index * _multiplier, std::move(surface));
\treturn {
\t\t.duration = _frameDuration,
\t\t.image = std::move(storage),
\t\t.last = (_frameIndex == _framesCount),
\t};'''

NEW_RENDER = '''\tconst auto ok = SafeRenderSync(
\t\t_rlottie,
\t\tindex * _multiplier,
\t\tstd::move(surface));
\tif (!ok) {
\t\t// This exact animation is broken (rlottie threw while rendering
\t\t// this frame). Stop trying to render further frames of it so we
\t\t// don't crash again on the next call - just end playback here.
\t\t_framesCount = _frameIndex;
\t}
\treturn {
\t\t.duration = _frameDuration,
\t\t.image = std::move(storage),
\t\t.last = (!ok) || (_frameIndex == _framesCount),
\t};'''


def main() -> None:
    lib_lottie = sys.argv[1]
    path = os.path.join(lib_lottie, 'lottie', 'lottie_frame_generator.cpp')
    src = open(path, encoding='utf-8').read()

    if 'SafeLoadFromData' in src:
        print('already patched')
        return

    inc_old = '#include "ui/image/image_prepare.h"\n'
    assert inc_old in src, 'include anchor not found'
    src = src.replace(inc_old, inc_old + '#include "base/debug_log.h"\n', 1)

    ns_old = 'namespace Lottie {\n\nFrameGenerator::FrameGenerator'
    assert ns_old in src, 'namespace anchor not found'
    src = src.replace(ns_old, 'namespace Lottie {\n' + GUARD + '\nFrameGenerator::FrameGenerator', 1)

    assert OLD_LOAD in src, 'load block not found'
    src = src.replace(OLD_LOAD, NEW_LOAD, 1)

    assert OLD_RENDER in src, 'render block not found'
    src = src.replace(OLD_RENDER, NEW_RENDER, 1)

    open(path, 'w', encoding='utf-8').write(src)
    print('patched OK:', path)


if __name__ == '__main__':
    main()
