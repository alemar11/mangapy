use crate::{
    parallel,
    provider::{Chapter, Http, Provider, Source, legacy_slug},
};
use anyhow::{Context, Result, ensure};
use caseless::Caseless;
use image::{ImageDecoder, metadata::Orientation};
use lopdf::{Document, Object, Stream, dictionary};
use percent_encoding::percent_decode_str;
use reqwest::Url;
use sha2::{Digest, Sha256};
use std::{
    collections::{HashMap, HashSet},
    fs,
    io::{Cursor, Write},
    path::{Path, PathBuf},
    sync::LazyLock,
};
use unicode_normalization::UnicodeNormalization;

pub fn directory(path: &Path) -> Result<PathBuf> {
    fs::create_dir_all(path)?;
    ensure!(
        fs::symlink_metadata(path)?.is_dir(),
        "Not a real directory: {}",
        path.display()
    );
    Ok(path.canonicalize()?)
}

fn regular_file_exists(path: &Path) -> Result<bool> {
    match fs::symlink_metadata(path) {
        Ok(meta) => {
            ensure!(meta.is_file(), "Not a regular file: {}", path.display());
            Ok(true)
        }
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => Ok(false),
        Err(err) => Err(err.into()),
    }
}

pub fn lock(root: &Path) -> Result<fs::File> {
    let path = root.join(".mangapy.lock");
    regular_file_exists(&path)?;
    let file = fs::OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(false)
        .open(path)?;
    file.lock()?;
    Ok(file)
}

fn shortened(name: &str) -> String {
    if name.len() <= 180 {
        return name.to_owned();
    }
    let end = name.floor_char_boundary(167);
    format!(
        "{}-{}",
        name[..end].trim_end_matches([' ', '.', '_']),
        digest(name)
    )
}

fn digest(name: &str) -> String {
    format!("{:x}", Sha256::digest(name.as_bytes()))[..12].to_owned()
}

fn component(name: &str) -> String {
    let sanitized: String = name
        .nfkc()
        .map(|ch| {
            if ch.is_control() || "<>:\"/\\|?*".contains(ch) {
                '_'
            } else {
                ch
            }
        })
        .collect();
    let spaces = sanitized.split_whitespace().collect::<Vec<_>>().join(" ");
    static UNDERSCORES: LazyLock<regex::Regex> = LazyLock::new(|| regex::Regex::new("_+").unwrap());
    let name = UNDERSCORES.replace_all(&spaces, "_");
    let name = name.trim_matches([' ', '.', '_']);
    let stem = name
        .split('.')
        .next()
        .unwrap_or_default()
        .to_ascii_uppercase();
    let reserved = matches!(stem.as_str(), "CON" | "PRN" | "AUX" | "NUL")
        || (stem.len() == 4
            && (stem.starts_with("COM") || stem.starts_with("LPT"))
            && matches!(stem.as_bytes()[3], b'1'..=b'9'));
    match name {
        "" => "unknown".to_owned(),
        _ if reserved => shortened(&format!("_{name}")),
        _ => shortened(name),
    }
}

pub fn manga_directory(root: &Path, source: Source, title: &str) -> Result<PathBuf> {
    let source = directory(&directory(root)?.join(source.name()))?;
    let normalized: String = title.nfkc().default_case_fold().collect();
    static SEPARATORS: LazyLock<regex::Regex> =
        LazyLock::new(|| regex::Regex::new(r"[\W]+").unwrap());
    let slug = SEPARATORS.replace_all(&normalized, "_");
    let slug = slug.trim_matches('_');
    let preferred = source.join(if slug.chars().any(char::is_alphanumeric) {
        component(slug)
    } else {
        format!("manga_{}", digest(&normalized))
    });
    let legacy = legacy_slug(title);
    if !legacy.is_empty() && fs::symlink_metadata(&preferred).is_err() {
        let path = source.join(legacy);
        if fs::symlink_metadata(&path).is_ok_and(|m| m.is_dir()) {
            return directory(&path);
        }
    }
    directory(&preferred)
}

pub fn chapter_name(chapter: &Chapter, source: Source) -> String {
    component(&source.chapter_output_label(chapter))
}

#[derive(Debug, PartialEq, Eq)]
pub enum ArchiveStatus {
    Downloaded,
    Existing,
    Unavailable,
}

pub struct Archiver<'a> {
    pub root: &'a Path,
    pub http: &'a Http,
    pub page_workers: usize,
    pub pdf: bool,
    pub force: bool,
}

impl Archiver<'_> {
    pub fn archive(
        &self,
        provider: &dyn Provider,
        chapter: &Chapter,
        name: &str,
    ) -> Result<ArchiveStatus> {
        ensure!(
            !name.is_empty() && !matches!(name, "." | "..") && !name.contains(['/', '\\', ':']),
            "Invalid chapter output name"
        );
        let pdf = if self.pdf {
            Some(directory(&self.root.join("pdf"))?.join(format!("{name}.pdf")))
        } else {
            None
        };
        let existing_pdf = match pdf.as_deref() {
            Some(path) => existing_pdf_pages(path, self.force)?,
            None => None,
        };
        if existing_pdf.is_some() && (existing_pdf == chapter.count || !chapter.is_downloadable()) {
            return Ok(ArchiveStatus::Existing);
        }
        if !chapter.is_downloadable() {
            return Ok(ArchiveStatus::Unavailable);
        }
        let pages = provider.pages(chapter)?;
        if let Some(count) = chapter.count {
            ensure!(
                count == pages.len(),
                "Expected {count} pages, got {}",
                pages.len()
            );
        }
        if pages.is_empty() {
            return Ok(ArchiveStatus::Unavailable);
        }
        if existing_pdf == Some(pages.len()) {
            return Ok(ArchiveStatus::Existing);
        }
        let image_root = directory(&self.root.join(if self.pdf { ".images" } else { "images" }))?;
        let chapter_dir = directory(&image_root.join(name))?;
        let paths: Vec<_> = pages
            .iter()
            .enumerate()
            .map(|(index, url)| page_path(&chapter_dir, index, url))
            .collect();
        let downloaded = self.download_pages(provider, &pages, &paths)?;
        if let Some(path) = pdf {
            write_pdf_from_pages(&paths, &path, true)?;
            for page in &paths {
                if let Err(error) = fs::remove_file(page) {
                    eprintln!(
                        "Could not remove temporary page {}: {error}",
                        page.display()
                    );
                }
            }
            let _ = fs::remove_dir(&chapter_dir);
            return Ok(ArchiveStatus::Downloaded);
        }
        prune_stale(&chapter_dir, &paths)?;
        if downloaded {
            Ok(ArchiveStatus::Downloaded)
        } else {
            Ok(ArchiveStatus::Existing)
        }
    }

    fn download_pages(
        &self,
        provider: &dyn Provider,
        pages: &[Url],
        paths: &[PathBuf],
    ) -> Result<bool> {
        ensure!(self.page_workers > 0, "Page concurrency must be positive");
        let jobs: Vec<_> = pages.iter().zip(paths).collect();
        let mut downloaded = false;
        let mut failures = Vec::new();
        for batch in jobs.chunks(self.page_workers) {
            let results = parallel::map(batch, |(url, path)| self.fetch(provider, url, path));
            for ((_, path), result) in batch.iter().zip(results) {
                match result {
                    Ok(new) => downloaded |= new,
                    Err(err) => failures.push(format!("{}: {err:#}", path.display())),
                }
            }
        }
        ensure!(
            failures.is_empty(),
            "{} of {} pages failed: {}",
            failures.len(),
            paths.len(),
            failures.join("; ")
        );
        Ok(downloaded)
    }

    fn fetch(&self, provider: &dyn Provider, url: &Url, path: &Path) -> Result<bool> {
        if regular_file_exists(path)?
            && !self.force
            && image::load_from_memory(&fs::read(path)?).is_ok()
        {
            return Ok(false);
        }
        ensure!(
            matches!(url.scheme(), "http" | "https"),
            "Invalid page URL scheme"
        );
        let data = self.http.get(url, provider.page_headers(url))?.bytes()?;
        image::load_from_memory(&data)
            .with_context(|| format!("Invalid image for {}", path.display()))?;
        let mut file =
            tempfile::NamedTempFile::new_in(path.parent().context("Missing image directory")?)?;
        file.write_all(&data)?;
        file.persist(path)?;
        Ok(true)
    }
}

fn existing_pdf_pages(path: &Path, force: bool) -> Result<Option<usize>> {
    if regular_file_exists(path)? && !force {
        return Ok(Document::load(path)
            .ok()
            .map(|pdf| pdf.get_pages().len())
            .filter(|&n| n > 0));
    }
    Ok(None)
}

fn prune_stale(root: &Path, expected: &[PathBuf]) -> Result<()> {
    let exact: HashSet<_> = expected
        .iter()
        .filter_map(|path| path.file_name())
        .collect();
    let folded: HashMap<_, _> = expected
        .iter()
        .filter_map(|path| Some((path.file_name()?.to_str()?.to_ascii_lowercase(), path)))
        .collect();
    let entries: Vec<_> = fs::read_dir(root)?.collect::<std::io::Result<_>>()?;
    let names: HashSet<_> = entries.iter().map(std::fs::DirEntry::file_name).collect();
    for entry in entries {
        let path = entry.path();
        let name = entry.file_name();
        let managed = path
            .file_stem()
            .and_then(|part| part.to_str())
            .is_some_and(|stem| !stem.is_empty() && stem.bytes().all(|b| b.is_ascii_digit()))
            && path
                .extension()
                .and_then(|ext| ext.to_str())
                .is_some_and(|ext| {
                    matches!(
                        ext.to_ascii_lowercase().as_str(),
                        "jpg"
                            | "jpeg"
                            | "png"
                            | "gif"
                            | "webp"
                            | "bmp"
                            | "img"
                            | "avif"
                            | "tiff"
                            | "tif"
                            | "heic"
                            | "heif"
                            | "j2k"
                            | "jfif"
                            | "jp2"
                            | "jpe"
                            | "jpf"
                            | "jpx"
                    )
                });
        if !managed || exact.contains(name.as_os_str()) || !entry.file_type()?.is_file() {
            continue;
        }
        if let Some(target) = name
            .to_str()
            .and_then(|name| folded.get(&name.to_ascii_lowercase()))
            && let Some(target_name) = target.file_name()
            && !names.contains(target_name)
            && same_file::is_same_file(&path, target)?
        {
            continue;
        }
        fs::remove_file(path)?;
    }
    Ok(())
}

fn page_path(root: &Path, index: usize, url: &Url) -> PathBuf {
    let decoded = percent_decode_str(url.path()).decode_utf8_lossy();
    let extension = Path::new(decoded.as_ref())
        .extension()
        .and_then(|part| part.to_str())
        .filter(|ext| {
            !ext.is_empty() && ext.len() <= 10 && ext.bytes().all(|b| b.is_ascii_alphanumeric())
        })
        .unwrap_or("img")
        .to_ascii_lowercase();
    root.join(format!("{index}.{extension}"))
}

pub fn write_pdf(images: &[PathBuf], target: &Path) -> Result<()> {
    write_pdf_from_pages(images, target, false)
}

fn write_pdf_from_pages(images: &[PathBuf], target: &Path, validated: bool) -> Result<()> {
    let mut pdf = Document::with_version("1.5");
    let tree = pdf.new_object_id();
    let mut kids = Vec::with_capacity(images.len());
    for image in images {
        let bytes = fs::read(image)?;
        let format = image::guess_format(&bytes)?;
        let mut decoder =
            image::ImageReader::with_format(Cursor::new(&bytes), format).into_decoder()?;
        let orientation = decoder.orientation()?;
        let color = decoder.color_type();
        let embed_jpeg = format == image::ImageFormat::Jpeg
            && orientation == Orientation::NoTransforms
            && matches!(color, image::ColorType::Rgb8 | image::ColorType::L8);
        let (image_width, image_height) = decoder.dimensions();
        let decoded = if validated && embed_jpeg {
            // Downloaded and cached pages already passed a full decode in fetch().
            drop(decoder);
            None
        } else {
            let mut decoded = image::DynamicImage::from_decoder(decoder)?;
            decoded.apply_orientation(orientation);
            Some(decoded)
        };
        let (width, height) = decoded
            .as_ref()
            .map_or((image_width, image_height), |image| {
                (image.width(), image.height())
            });
        let mut fields = dictionary! {
            "Type" => "XObject", "Subtype" => "Image",
            "Width" => width, "Height" => height,
            "BitsPerComponent" => 8,
            "ColorSpace" => "DeviceRGB",
        };
        let mut stream = if embed_jpeg {
            if color == image::ColorType::L8 {
                fields.set("ColorSpace", "DeviceGray");
            }
            fields.set("Filter", "DCTDecode");
            Stream::new(fields, bytes)
        } else {
            let decoded = decoded.expect("non-embedded images are decoded");
            if decoded.color().has_alpha() {
                let rgba = decoded.to_rgba8();
                let alpha: Vec<_> = rgba.pixels().map(|pixel| pixel[3]).collect();
                if alpha.iter().any(|&value| value != 255) {
                    let mut mask = Stream::new(
                        dictionary! {
                            "Type" => "XObject", "Subtype" => "Image", "ColorSpace" => "DeviceGray",
                            "Width" => width, "Height" => height, "BitsPerComponent" => 8,
                        },
                        alpha,
                    );
                    mask.compress()?;
                    fields.set("SMask", pdf.add_object(mask));
                }
            }
            Stream::new(fields, decoded.into_rgb8().into_raw())
        };
        stream.compress()?;
        let image_id = pdf.add_object(stream);
        let width = width as f32 * 0.72;
        let height = height as f32 * 0.72;
        let draw = pdf.add_object(Stream::new(
            dictionary! {},
            format!("q\n{width:.4} 0 0 {height:.4} 0 0 cm\n/Im0 Do\nQ\n").into_bytes(),
        ));
        let page = pdf.add_object(dictionary! {
            "Type" => "Page", "Parent" => tree, "Contents" => draw,
            "MediaBox" => vec![0.into(), 0.into(), width.into(), height.into()],
            "Resources" => dictionary! { "XObject" => dictionary! { "Im0" => image_id } },
        });
        kids.push(Object::Reference(page));
    }
    pdf.objects.insert(
        tree,
        dictionary! { "Type" => "Pages", "Count" => kids.len() as u32, "Kids" => kids }.into(),
    );
    let catalog = pdf.add_object(dictionary! { "Type" => "Catalog", "Pages" => tree });
    pdf.trailer.set("Root", catalog);
    let mut temporary =
        tempfile::NamedTempFile::new_in(target.parent().context("Missing PDF directory")?)?;
    pdf.save_to(temporary.as_file_mut())?;
    temporary.as_file().sync_all()?;
    ensure!(
        Document::load(temporary.path())?.get_pages().len() == images.len(),
        "PDF page count mismatch"
    );
    regular_file_exists(target)?;
    temporary.persist(target)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cleanup_preserves_the_expected_file_under_both_case_policies() {
        let root = tempfile::tempdir().unwrap();
        let uppercase = root.path().join("0.JPG");
        let lowercase = root.path().join("0.jpg");
        let stale = root.path().join("1.jpg");
        fs::write(&uppercase, b"page").unwrap();
        fs::write(&stale, b"stale").unwrap();
        let aliases = lowercase.exists();
        if !aliases {
            fs::write(&lowercase, b"page").unwrap();
        }
        prune_stale(root.path(), std::slice::from_ref(&lowercase)).unwrap();
        assert_eq!(fs::read(lowercase).unwrap(), b"page");
        assert_eq!(uppercase.exists(), aliases);
        assert!(!stale.exists());
    }

    #[test]
    fn filename_normalization_preserves_stable_component_names() {
        assert_eq!(component("Ａ:  B"), "A_ B");
        assert_eq!(component("nul.txt"), "_nul.txt");
        let original = "界".repeat(100);
        let result = component(&original);
        assert!(result.len() <= 180);
        assert!(result.ends_with(&digest(&original)));
        assert_eq!(component(&result), result);
    }

    #[test]
    fn pdf_contains_one_page_per_image() {
        let temp = tempfile::tempdir().unwrap();
        let jpeg = temp.path().join("0.jpg");
        let png = temp.path().join("1.png");
        let image = image::RgbImage::from_pixel(10, 20, image::Rgb([10, 50, 90]));
        image.save(&jpeg).unwrap();
        image::RgbaImage::from_pixel(10, 20, image::Rgba([10, 50, 90, 100]))
            .save(&png)
            .unwrap();
        let pdf = temp.path().join("chapter.pdf");
        let pages = [jpeg, png];
        write_pdf(&pages, &pdf).unwrap();
        let from_archive = temp.path().join("validated.pdf");
        write_pdf_from_pages(&pages, &from_archive, true).unwrap();
        assert_eq!(fs::read(&pdf).unwrap(), fs::read(from_archive).unwrap());
        let document = Document::load(&pdf).unwrap();
        assert_eq!(document.get_pages().len(), 2);
        assert!(
            document
                .objects
                .values()
                .filter_map(|object| object.as_stream().ok())
                .any(|stream| stream.dict.has(b"SMask"))
        );
    }

    #[test]
    fn incomplete_pdf_keeps_valid_pages_and_reuses_them_on_retry() {
        use crate::test_http::Server;
        use std::{
            io::Cursor,
            sync::{
                Arc,
                atomic::{AtomicUsize, Ordering},
            },
        };

        struct Pages(Vec<Url>);

        impl Provider for Pages {
            fn search(&self, _: &str) -> Result<crate::provider::Manga> {
                unreachable!()
            }
            fn pages(&self, _: &Chapter) -> Result<Vec<Url>> {
                Ok(self.0.clone())
            }
        }

        let mut bytes = Cursor::new(Vec::new());
        image::DynamicImage::new_rgb8(10, 20)
            .write_to(&mut bytes, image::ImageFormat::Png)
            .unwrap();
        let bytes = bytes.into_inner();
        let first_hits = Arc::new(AtomicUsize::new(0));
        let last_hits = Arc::new(AtomicUsize::new(0));
        let server = Server::start({
            let first_hits = Arc::clone(&first_hits);
            let last_hits = Arc::clone(&last_hits);
            move |path| match path {
                "/0.png" => {
                    first_hits.fetch_add(1, Ordering::Relaxed);
                    (200, bytes.clone())
                }
                "/1.png" if last_hits.fetch_add(1, Ordering::Relaxed) == 0 => {
                    (200, b"invalid image".to_vec())
                }
                "/1.png" => (200, bytes.clone()),
                _ => (404, vec![]),
            }
        });
        let urls =
            ["/0.png", "/1.png"].map(|path| Url::parse(&format!("{}{path}", server.url)).unwrap());
        let chapter = Chapter {
            id: "1".to_owned(),
            label: "1".to_owned(),
            number: Some(1.0),
            volume: None,
            url: urls[0].clone(),
            count: Some(2),
            external: false,
        };
        let provider = Pages(urls.to_vec());
        let temp = tempfile::tempdir().unwrap();
        let http = Http::new(reqwest::blocking::Client::new(), false);
        let archiver = Archiver {
            root: temp.path(),
            http: &http,
            page_workers: 1,
            pdf: true,
            force: false,
        };
        let pdf = temp.path().join("pdf/1.pdf");
        assert!(archiver.archive(&provider, &chapter, "1").is_err());
        assert!(!pdf.exists());
        assert!(temp.path().join(".images/1/0.png").is_file());

        assert_eq!(
            archiver.archive(&provider, &chapter, "1").unwrap(),
            ArchiveStatus::Downloaded
        );
        assert_eq!(Document::load(pdf).unwrap().get_pages().len(), 2);
        assert!(!temp.path().join(".images/1").exists());
        assert_eq!(
            archiver.archive(&provider, &chapter, "1").unwrap(),
            ArchiveStatus::Existing
        );
        assert_eq!(first_hits.load(Ordering::Relaxed), 1);
        assert_eq!(last_hits.load(Ordering::Relaxed), 2);
    }

    #[cfg(unix)]
    #[test]
    fn refuses_symlinked_output_directories_and_files() {
        use std::os::unix::fs::symlink;
        let temp = tempfile::tempdir().unwrap();
        let outside = tempfile::tempdir().unwrap();
        let dir = temp.path().join("fanfox");
        symlink(outside.path(), &dir).unwrap();
        assert!(manga_directory(temp.path(), Source::Fanfox, "Title").is_err());
        assert!(!outside.path().join("title").exists());

        let file = temp.path().join("page.png");
        symlink(outside.path().join("page.png"), &file).unwrap();
        assert!(regular_file_exists(&file).is_err());
    }

    #[test]
    fn output_path_matches_existing_layout() {
        let temp = tempfile::tempdir().unwrap();
        assert_eq!(
            manga_directory(temp.path(), Source::Fanfox, "Straße!").unwrap(),
            temp.path().canonicalize().unwrap().join("fanfox/strasse")
        );
        let url = Url::parse("https://example.org/page%2EJPG?size=1").unwrap();
        assert_eq!(page_path(temp.path(), 0, &url), temp.path().join("0.jpg"));
    }
}
