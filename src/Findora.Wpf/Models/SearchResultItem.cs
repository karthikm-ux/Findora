using System;
using System.Collections.Generic;
using System.IO;
using System.Windows.Media;

namespace Findora.Wpf.Models
{
    public class SearchResultItem
    {
        public string Filename { get; set; } = string.Empty;
        public string FullPath { get; set; } = string.Empty;
        public long SizeBytes { get; set; }
        public double MTime { get; set; }
        public string Extension { get; set; } = string.Empty;
        public ImageSource? Icon { get; set; }

        public string FormattedSize
        {
            get
            {
                if (SizeBytes <= 0)
                {
                    if (string.IsNullOrEmpty(Extension) && Directory.Exists(FullPath))
                        return "Folder";
                    return "0 B";
                }
                if (SizeBytes < 1024) return $"{SizeBytes} B";
                if (SizeBytes < 1024 * 1024) return $"{SizeBytes / 1024.0:F1} KB";
                if (SizeBytes < 1024 * 1024 * 1024) return $"{SizeBytes / (1024.0 * 1024):F1} MB";
                return $"{SizeBytes / (1024.0 * 1024 * 1024):F2} GB";
            }
        }

        public string FileTypeDescription
        {
            get
            {
                if (string.IsNullOrEmpty(Extension))
                {
                    if (Directory.Exists(FullPath)) return "File Folder";
                    return "File";
                }

                string ext = Extension.ToLowerInvariant().TrimStart('.');
                return ext switch
                {
                    "pdf" => "PDF Document",
                    "png" => "PNG Image",
                    "jpg" or "jpeg" => "JPEG Image",
                    "gif" => "GIF Image",
                    "svg" => "SVG Vector",
                    "webp" => "WebP Image",
                    "docx" or "doc" => "Word Document",
                    "pptx" or "ppt" => "PowerPoint",
                    "xlsx" or "xls" or "csv" => "Excel Spreadsheet",
                    "py" => "Python File",
                    "cs" => "C# Source",
                    "cpp" or "c" or "h" => "C/C++ Source",
                    "java" => "Java Source",
                    "js" => "JavaScript File",
                    "ts" => "TypeScript File",
                    "html" or "htm" => "HTML Document",
                    "css" => "CSS Stylesheet",
                    "json" => "JSON File",
                    "xml" => "XML Document",
                    "txt" => "Text Document",
                    "md" => "Markdown File",
                    "zip" or "rar" or "7z" or "tar" or "gz" => "Archive",
                    "exe" => "Application",
                    "msi" => "Installer",
                    "mp4" or "mkv" or "avi" or "mov" => "Video File",
                    "mp3" or "wav" or "flac" or "aac" => "Audio File",
                    _ => $"{ext.ToUpperInvariant()} File"
                };
            }
        }

        public string FormattedDate
        {
            get
            {
                if (MTime <= 0) return string.Empty;
                try
                {
                    var dt = DateTimeOffset.FromUnixTimeSeconds((long)MTime).LocalDateTime;
                    return dt.ToString("yyyy-MM-dd");
                }
                catch
                {
                    return string.Empty;
                }
            }
        }

        public string DisplayPath
        {
            get
            {
                if (string.IsNullOrEmpty(FullPath)) return string.Empty;
                if (FullPath.Length <= 80) return FullPath;
                return FullPath.Substring(0, 36) + "..." + FullPath.Substring(FullPath.Length - 40);
            }
        }
    }

    public class SearchQueryResult
    {
        public List<SearchResultItem> Items { get; set; } = new();
        public int TotalMatches { get; set; }
        public double IndexMs { get; set; }
        public double MetaMs { get; set; }
        public double TotalMs { get; set; }
        public double ClientElapsedMs { get; set; }

        public string ProminentSearchTime => TotalMs < 0.05 ? "< 0.1 ms" : $"{TotalMs:F2} ms";
        public string FormattedIndexMs => IndexMs < 0.05 ? "< 0.1 ms" : $"{IndexMs:F2} ms";
        public string FormattedTotalMs => TotalMs < 0.05 ? "< 0.1 ms" : $"{TotalMs:F2} ms";

        public string ResultsHeader
        {
            get
            {
                if (TotalMatches == 0) return "0 results";
                if (TotalMatches == 1) return "1 result";
                return $"{TotalMatches:N0} results";
            }
        }

        public string FormattedMetrics
        {
            get
            {
                if (TotalMatches == 0) return string.Empty;
                string indexStr = IndexMs < 0.05 ? "< 0.1 ms" : $"{IndexMs:F2} ms";
                string totalStr = TotalMs < 0.05 ? "< 0.1 ms" : $"{TotalMs:F2} ms";
                return $"{TotalMatches} match{(TotalMatches == 1 ? "" : "es")}  •  Index: {indexStr}  •  Total: {totalStr}";
            }
        }
    }
}
