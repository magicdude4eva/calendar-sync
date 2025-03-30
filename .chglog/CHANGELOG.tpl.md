# CHANGELOG

{{ range .Versions }}
## {{ .Tag.Name }} - {{ datetime "2006-01-02" .Tag.Date }}
{{ if .Tag.Subject }}
> {{ .Tag.Subject }}
{{ end }}

{{ range .CommitGroups }}
### {{ .Title }}

{{ range .Commits }}
- {{ .Subject }}
{{ end }}
{{ end }}

{{ if .RevertCommits }}
### Reverts

{{ range .RevertCommits }}
- {{ .Revert.Subject }}
{{ end }}
{{ end }}

{{ if .NoteGroups }}
### Notes

{{ range .NoteGroups }}
#### {{ .Title }}

{{ range .Notes }}
- {{ .Body }}
{{ end }}
{{ end }}
{{ end }}
{{ end }}
