// SPDX-License-Identifier: GPL-2.0-or-later
// Implements the PNG single-page pdftoppm calls used by Studio.
#include <poppler-document.h>
#include <poppler-page.h>
#include <poppler-page-renderer.h>
#include <poppler-version.h>
#include <mach-o/dyld.h>

#include <algorithm>
#include <filesystem>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
std::filesystem::path data_dir()
{
    uint32_t size = 0;
    _NSGetExecutablePath(nullptr, &size);
    std::vector<char> path(size);
    if (_NSGetExecutablePath(path.data(), &size) != 0) {
        throw std::runtime_error("cannot locate bundled Poppler data");
    }
    return std::filesystem::canonical(path.data()).parent_path().parent_path() / "poppler-data";
}

int positive(const std::string &value)
{
    std::size_t end = 0;
    const int number = std::stoi(value, &end);
    if (number <= 0 || end != value.size()) {
        throw std::runtime_error("expected a positive integer: " + value);
    }
    return number;
}
}

int main(int argc, char **argv)
{
    try {
        if (argc == 2 && std::string(argv[1]) == "-v") {
            std::cout << "Studio pdftoppm (Poppler " << poppler::version_string() << ")\n";
            return 0;
        }
        int first = 1, last = 0, dpi = 150, scale = 0;
        bool png = false, single = false;
        std::vector<std::string> paths;
        for (int i = 1; i < argc; ++i) {
            const std::string arg = argv[i];
            if (arg == "-png") {
                png = true;
            } else if (arg == "-singlefile") {
                single = true;
            } else if (arg == "-f" || arg == "-l" || arg == "-r" || arg == "-scale-to") {
                if (++i == argc) {
                    throw std::runtime_error("missing value: " + arg);
                }
                int &option = arg == "-f" ? first : arg == "-l" ? last : arg == "-r" ? dpi : scale;
                option = positive(argv[i]);
            } else if (arg.empty() || arg[0] == '-') {
                throw std::runtime_error("unsupported argument: " + arg);
            } else {
                paths.push_back(arg);
            }
        }
        if (!png || !single || paths.size() != 2 || (last && last < first)) {
            throw std::runtime_error("expected -png -singlefile and input/output paths");
        }

        const auto data = data_dir();
        if (!std::filesystem::is_regular_file(data / "cidToUnicode/Adobe-GB1") ||
            !std::filesystem::is_directory(data / "cMap/Adobe-GB1") ||
            !poppler::set_data_dir(data.string())) {
            throw std::runtime_error("cannot initialize bundled Poppler character maps");
        }
        const std::unique_ptr<poppler::document> doc(poppler::document::load_from_file(paths[0]));
        if (!doc || doc->is_locked() || first > doc->pages()) {
            throw std::runtime_error("cannot open requested PDF page");
        }
        const std::unique_ptr<poppler::page> page(doc->create_page(first - 1));
        if (!page) {
            throw std::runtime_error("cannot load requested PDF page");
        }
        double resolution = dpi;
        if (scale) {
            const auto box = page->page_rect(poppler::media_box);
            const double longest = std::max(box.width(), box.height());
            if (longest <= 0) {
                throw std::runtime_error("invalid PDF page dimensions");
            }
            resolution = 72.0 * scale / longest;
        }
        poppler::page_renderer renderer;
        renderer.set_image_format(poppler::image::format_rgb24);
        renderer.set_render_hints(poppler::page_renderer::antialiasing |
                                  poppler::page_renderer::text_antialiasing);
        const auto image = renderer.render_page(page.get(), resolution, resolution);
        if (!image.is_valid() || !image.save(paths[1] + ".png", "png")) {
            throw std::runtime_error("could not write PNG");
        }
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "Studio pdftoppm: " << error.what() << '\n';
        return 1;
    }
}
