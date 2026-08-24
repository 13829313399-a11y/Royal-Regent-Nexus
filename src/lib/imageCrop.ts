export interface NormalizedCropSelection {
  x: number
  y: number
  width: number
  height: number
}

export interface ContainedImageFrame {
  left: number
  top: number
  width: number
  height: number
}

export function getRotatedImageSize(width: number, height: number, degrees: number) {
  const normalizedDegrees = ((degrees % 360) + 360) % 360
  const swapsAxes = normalizedDegrees === 90 || normalizedDegrees === 270
  return swapsAxes
    ? { width: height, height: width }
    : { width, height }
}

export function clampRatio(value: number) {
  if (!Number.isFinite(value)) return 0
  return Math.min(1, Math.max(0, value))
}

export function normalizeCropSelection(
  start: { x: number, y: number },
  end: { x: number, y: number },
): NormalizedCropSelection {
  const startX = clampRatio(start.x)
  const startY = clampRatio(start.y)
  const endX = clampRatio(end.x)
  const endY = clampRatio(end.y)

  return {
    x: Math.min(startX, endX),
    y: Math.min(startY, endY),
    width: Math.abs(endX - startX),
    height: Math.abs(endY - startY),
  }
}

export function isUsableCropSelection(selection: NormalizedCropSelection | null, minRatio = 0.08) {
  return Boolean(selection && selection.width >= minRatio && selection.height >= minRatio)
}

export function getContainedImageFrame(
  containerWidth: number,
  containerHeight: number,
  naturalWidth: number,
  naturalHeight: number,
): ContainedImageFrame {
  if (containerWidth <= 0 || containerHeight <= 0 || naturalWidth <= 0 || naturalHeight <= 0) {
    return {
      left: 0,
      top: 0,
      width: Math.max(0, containerWidth),
      height: Math.max(0, containerHeight),
    }
  }

  const scale = Math.min(containerWidth / naturalWidth, containerHeight / naturalHeight)
  const width = naturalWidth * scale
  const height = naturalHeight * scale

  return {
    left: (containerWidth - width) / 2,
    top: (containerHeight - height) / 2,
    width,
    height,
  }
}

export function selectionToImagePixels(
  selection: NormalizedCropSelection,
  naturalWidth: number,
  naturalHeight: number,
  paddingRatio = 0.015,
) {
  const paddingX = Math.round(naturalWidth * paddingRatio)
  const paddingY = Math.round(naturalHeight * paddingRatio)
  const left = Math.max(0, Math.floor(selection.x * naturalWidth) - paddingX)
  const top = Math.max(0, Math.floor(selection.y * naturalHeight) - paddingY)
  const right = Math.min(naturalWidth, Math.ceil((selection.x + selection.width) * naturalWidth) + paddingX)
  const bottom = Math.min(naturalHeight, Math.ceil((selection.y + selection.height) * naturalHeight) + paddingY)

  return {
    x: left,
    y: top,
    width: Math.max(1, right - left),
    height: Math.max(1, bottom - top),
  }
}

export async function cropImageBlob(
  imageBlob: Blob,
  selection: NormalizedCropSelection,
  fileName: string,
  outputType = 'image/png',
) {
  const imageBitmap = await createImageBitmap(imageBlob)
  const source = selectionToImagePixels(selection, imageBitmap.width, imageBitmap.height)
  const canvas = document.createElement('canvas')
  canvas.width = source.width
  canvas.height = source.height

  const context = canvas.getContext('2d')
  if (!context) {
    throw new Error('当前浏览器无法创建图片裁剪画布')
  }

  context.drawImage(
    imageBitmap,
    source.x,
    source.y,
    source.width,
    source.height,
    0,
    0,
    source.width,
    source.height,
  )
  imageBitmap.close()

  const croppedBlob = await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) {
        resolve(blob)
        return
      }
      reject(new Error('图片裁剪失败，请重新选择照片'))
    }, outputType, 0.94)
  })

  return new File([croppedBlob], fileName, {
    type: croppedBlob.type || outputType,
    lastModified: Date.now(),
  })
}

export async function rotateImageBlob(
  imageBlob: Blob,
  degrees: -90 | 90 | 180,
  fileName: string,
  outputType = 'image/png',
) {
  const imageBitmap = await createImageBitmap(imageBlob)
  const outputSize = getRotatedImageSize(imageBitmap.width, imageBitmap.height, degrees)
  const canvas = document.createElement('canvas')
  canvas.width = outputSize.width
  canvas.height = outputSize.height

  const context = canvas.getContext('2d')
  if (!context) {
    imageBitmap.close()
    throw new Error('当前浏览器无法创建图片旋转画布')
  }

  context.translate(canvas.width / 2, canvas.height / 2)
  context.rotate((degrees * Math.PI) / 180)
  context.drawImage(imageBitmap, -imageBitmap.width / 2, -imageBitmap.height / 2)
  imageBitmap.close()

  const rotatedBlob = await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) {
        resolve(blob)
        return
      }
      reject(new Error('图片旋转失败，请重新选择照片'))
    }, outputType, 0.94)
  })

  return new File([rotatedBlob], fileName, {
    type: rotatedBlob.type || outputType,
    lastModified: Date.now(),
  })
}
