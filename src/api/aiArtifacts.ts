import axios from 'axios'
import { http } from '@/lib/http'

export type AIArtifactClassification = 'INTERNAL' | 'CONFIDENTIAL_BUSINESS' | 'RESTRICTED'
export type AIArtifactContentClass = 'WORKBOOK' | 'DOCUMENT' | 'IMAGE'

export interface AIArtifactData {
  id: string
  factory_id: string
  original_filename: string
  normalized_extension: string
  detected_mime_type: string
  content_class: AIArtifactContentClass
  size_bytes: number
  sha256: string
  classification: AIArtifactClassification
  status: 'ACTIVE' | 'DELETION_PENDING' | 'DELETED' | 'EXPIRED'
  scanner_status: 'CLEAN' | 'REJECTED'
  parser_status: 'NOT_REQUESTED' | 'PENDING' | 'READY' | 'FAILED'
  parent_artifact_id: string | null
  derivation_type: string
  parser_version: string
  model_version: string
  retention_until: string
  created_at: string
  updated_at: string
}

export async function uploadVisionArtifact(
  file: File,
  factoryId: string,
  classification: AIArtifactClassification = 'CONFIDENTIAL_BUSINESS',
) {
  const body = new FormData()
  body.append('factory_id', factoryId)
  body.append('classification', classification)
  body.append('file', file)
  const response = await http.post<AIArtifactData>('/ai/artifacts/vision-upload', body, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60_000,
  })
  return response.data
}

export async function uploadAIArtifact(
  file: File,
  factoryId: string,
  classification: AIArtifactClassification = 'CONFIDENTIAL_BUSINESS',
) {
  const body = new FormData()
  body.append('factory_id', factoryId)
  body.append('classification', classification)
  body.append('file', file)
  const response = await http.post<AIArtifactData>('/ai/artifacts', body, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60_000,
  })
  return response.data
}

export function isArtifactWorkflowUnavailable(error: unknown) {
  return axios.isAxiosError(error)
    && error.response?.status === 404
    && error.response?.data?.detail === 'Not Found'
}
