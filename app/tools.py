from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class GoogleWorkspaceTools:
    drive: Any
    docs: Any
    default_folder_id: str = ""

    def list_drive_files(self, folder_id: str | None = None, limit: int = 10) -> dict:
        folder = folder_id or self.default_folder_id
        query = "trashed=false"
        if folder:
            query += f" and '{folder}' in parents"

        res = (
            self.drive.files()
            .list(
                q=query,
                pageSize=limit,
                fields="files(id,name,mimeType,webViewLink)",
                orderBy="modifiedTime desc",
            )
            .execute()
        )
        return {"files": res.get("files", [])}

    def create_google_doc(self, title: str, initial_content: str = "", folder_id: str | None = None) -> dict:
        folder = folder_id or self.default_folder_id
        file_metadata = {
            "name": title,
            "mimeType": "application/vnd.google-apps.document",
        }
        if folder:
            file_metadata["parents"] = [folder]

        created = self.drive.files().create(body=file_metadata, fields="id,name,webViewLink").execute()
        doc_id = created["id"]

        if initial_content.strip():
            self.docs.documents().batchUpdate(
                documentId=doc_id,
                body={
                    "requests": [
                        {
                            "insertText": {
                                "location": {"index": 1},
                                "text": initial_content,
                            }
                        }
                    ]
                },
            ).execute()

        return {
            "doc_id": doc_id,
            "title": created.get("name", title),
            "link": created.get("webViewLink", f"https://docs.google.com/document/d/{doc_id}/edit"),
        }

    def append_google_doc(self, doc_id: str, content: str) -> dict:
        doc = self.docs.documents().get(documentId=doc_id).execute()
        end_index = doc.get("body", {}).get("content", [{}])[-1].get("endIndex", 1)
        self.docs.documents().batchUpdate(
            documentId=doc_id,
            body={
                "requests": [
                    {
                        "insertText": {
                            "location": {"index": max(1, end_index - 1)},
                            "text": "\n" + content,
                        }
                    }
                ]
            },
        ).execute()
        return {"doc_id": doc_id, "appended_chars": len(content)}

    def read_google_doc(self, doc_id: str) -> dict:
        doc = self.docs.documents().get(documentId=doc_id).execute()
        text_chunks = []
        for block in doc.get("body", {}).get("content", []):
            para = block.get("paragraph")
            if not para:
                continue
            for el in para.get("elements", []):
                tr = el.get("textRun")
                if tr and "content" in tr:
                    text_chunks.append(tr["content"])
        content = "".join(text_chunks).strip()
        return {"doc_id": doc_id, "content": content[:12000]}
