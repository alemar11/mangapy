use crate::provider::{Chapter, number};
use anyhow::{Context, Result, ensure};

pub enum Selection {
    All,
    Latest,
    Single(String),
    Range(f64, Option<f64>),
}

impl Selection {
    pub fn from_cli(value: String) -> Result<Self> {
        // A numeric prefix identifies a range; MangaDex UUIDs are labels.
        if value.len() == 36
            && value.split('-').map(str::len).eq([8, 4, 4, 4, 12])
            && value
                .bytes()
                .all(|byte| byte == b'-' || byte.is_ascii_hexdigit())
        {
            return Ok(Self::Single(value));
        }
        match value.split_once('-') {
            Some((start, _)) if number(start).is_some() => Self::range(&value),
            _ => Ok(Self::Single(value)),
        }
    }

    pub fn range(value: &str) -> Result<Self> {
        let (first, last) = value
            .split_once('-')
            .context("Expected chapter range START-END")?;
        let first = number(first).context("Invalid range start")?;
        let last = if last.trim().is_empty() {
            None
        } else {
            Some(number(last).context("Invalid range end")?)
        };
        ensure!(
            last.is_none_or(|last| last >= first),
            "Range end precedes its start"
        );
        Ok(Self::Range(first, last))
    }

    pub fn select<'a>(&self, chapters: &'a [Chapter]) -> Vec<&'a Chapter> {
        match self {
            Self::All => chapters.iter().collect(),
            Self::Latest => {
                let available = || chapters.iter().filter(|chapter| chapter.is_downloadable());
                available()
                    .filter_map(|chapter| Some((chapter.number?, chapter)))
                    .reduce(|left, right| if right.0 > left.0 { right } else { left })
                    .map(|(_, chapter)| chapter)
                    .or_else(|| available().next_back())
                    .into_iter()
                    .collect()
            }
            Self::Single(value) => {
                let value = value.trim();
                let wanted = number(value);
                chapters
                    .iter()
                    .find(|ch| ch.label == value || (wanted.is_some() && wanted == ch.number))
                    .into_iter()
                    .collect()
            }
            Self::Range(first, last) => chapters
                .iter()
                .filter(|chapter| {
                    chapter
                        .number
                        .is_some_and(|n| n >= *first && last.is_none_or(|last| n <= last))
                })
                .collect(),
        }
    }
}

pub fn sort_chapters(chapters: &mut [Chapter]) {
    let sorting = |chapter: &Chapter| match (chapter.number, chapter.volume) {
        (Some(number), volume) => (0, volume.unwrap_or(number), number),
        (None, Some(volume)) => (1, volume, 0.0),
        (None, None) => (2, 0.0, 0.0),
    };
    chapters.sort_by(|a, b| {
        let (a_kind, a_primary, a_number) = sorting(a);
        let (b_kind, b_primary, b_number) = sorting(b);
        a_kind
            .cmp(&b_kind)
            .then_with(|| a_primary.total_cmp(&b_primary))
            .then_with(|| a_number.total_cmp(&b_number))
            .then(a.label.cmp(&b.label))
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::test_http::chapter;

    #[test]
    fn volumes_order_equal_numbers_and_sort_extras_after_numbered_chapters() {
        let mut early = chapter("early", Some(2.5));
        early.volume = Some(1.0);
        let mut late = chapter("late", Some(2.5));
        late.volume = Some(2.0);
        let mut chapters = [late, chapter("extra", None), early];
        sort_chapters(&mut chapters);
        assert_eq!(
            chapters.each_ref().map(|ch| ch.id.as_str()),
            ["early", "late", "extra"]
        );
        assert_eq!(Selection::Latest.select(&chapters)[0].id, "early");
    }

    #[test]
    fn hyphenated_labels_and_digit_prefixed_uuids_are_single_chapters() {
        for label in ["special-edition", "12345678-1234-4abc-aaaa-abcd1234abcd"] {
            let chapters = [chapter(label, None)];
            let selection = Selection::from_cli(label.to_owned()).unwrap();
            assert_eq!(selection.select(&chapters)[0].id, label);
        }
    }
}
