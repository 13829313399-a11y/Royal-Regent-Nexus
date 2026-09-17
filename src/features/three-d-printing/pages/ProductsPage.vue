<script setup lang="ts">
import QuoteEditor from "../components/QuoteEditor.vue";
import { computed, ref, watch } from "vue";
import LegacyDialog from "../components/LegacyDialog.vue";
import { reactive } from "vue";
const brokenImages = reactive(new Set<string>());
import PageControls from "../components/PageControls.vue";
import { useWorkspaceContext } from "../context";
const {
  listPages,
  loadPage,
  showProductRecords,
  dashboard,
  saving,
  errorMessage,
  canOperate,
  canUploadImage,
  productForm,
  pendingProductImage,
  imageInputKey,
  money,
  resetProductForm,
  editProduct,
  submitProduct,
  archiveProduct,
  Save,
} = useWorkspaceContext();
const showForm = ref(false);
const imageError = ref("");
const imagePreview = ref("");
const existingImage = computed(
  () =>
    dashboard.value?.products.find((p) => p.id === productForm.id)?.image_url ||
    "",
);
watch(pendingProductImage, (file, _previous, onCleanup) => {
  imagePreview.value = file ? URL.createObjectURL(file) : "";
  const url = imagePreview.value;
  onCleanup(() => {
    if (url) URL.revokeObjectURL(url);
  });
});
watch(showForm, (open) => {
  imageError.value = "";
  if (!open) pendingProductImage.value = null;
});
watch(imageInputKey, () => {
  imageError.value = "";
});
function chooseImage(file: File | null) {
  if (!file || !canUploadImage.value || saving.value) return;
  imageError.value = "";
  if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
    imageError.value = "请选择 JPEG、PNG 或 WebP 图片。";
    return;
  }
  if (file.size > 5 * 1024 * 1024) {
    imageError.value = "图片超过 5MB，请缩小后再粘贴或上传。";
    return;
  }
  pendingProductImage.value = file;
  imageInputKey.value += 1;
}
function pasteImage(event: ClipboardEvent) {
  if (!canUploadImage.value || saving.value) return;
  const file = Array.from(event.clipboardData?.items ?? [])
    .find((item) => item.kind === "file" && item.type.startsWith("image/"))
    ?.getAsFile();
  if (!file) return;
  event.preventDefault();
  chooseImage(file);
}
function selectImage(event: Event) {
  chooseImage((event.target as HTMLInputElement).files?.[0] ?? null);
}
function clearImage() {
  pendingProductImage.value = null;
  imageError.value = "";
  imageInputKey.value += 1;
}
function openAdd() {
  resetProductForm();
  showForm.value = true;
}
watch(
  () => productForm.id,
  (value) => {
    if (value) showForm.value = true;
  },
);
async function saveForm() {
  await submitProduct();
  if (!errorMessage.value) showForm.value = false;
}
</script>
<template>
  <template v-if="dashboard">
    <section class="space-y-5">
      <div class="legacy-toolbar">
        <button v-if="canOperate" class="action-button" @click="openAdd">
          + 添加产品
        </button>
      </div>
      <form
        class="collection-filters flex flex-wrap gap-3 rounded-xl border bg-white p-3"
        @submit.prevent="loadPage('products')"
      >
        <input
          v-model="listPages.products!.q"
          placeholder="搜索名称 / 客户 / 材料"
          class="rounded border p-2"
        /><select v-model="listPages.products!.quality" class="rounded border">
          <option value="">全部质量</option>
          <option value="missing_image">缺图</option>
          <option value="duplicate">重复名称</option>
          <option value="incomplete">资料不完整</option></select
        ><button type="submit" class="rounded border px-4">查询</button>
      </form>
      <PageControls
        :page="listPages.products!.page"
        :total="listPages.products!.total"
        :busy="listPages.products!.busy"
        @change="loadPage('products', $event)"
      />
      <LegacyDialog
        v-if="showForm"
        title="产品"
        @close="showForm = false"
        @paste="pasteImage"
      >
        <form
          v-if="canOperate"
          class="panel-card p-5"
          @submit.prevent="saveForm"
        >
          <div class="section-heading">
            <div>
              <h2>{{ productForm.id ? "编辑产品" : "新增产品" }}</h2>
              <p>填写产品资料；复制图片后可直接在此窗口按 Ctrl+V 粘贴。</p>
            </div>
            <button
              v-if="productForm.id"
              class="action-button secondary"
              type="button"
              @click="resetProductForm"
            >
              取消编辑
            </button>
          </div>
          <div class="form-grid">
            <label
              >产品名称<input
                v-model="productForm.name"
                required
                maxlength="255"
            /></label>
            <label
              >客户<input v-model="productForm.customer" maxlength="255"
            /></label>
            <label
              >材料<select v-model="productForm.material_name">
                <option value="">未指定</option>
                <option
                  v-for="item in dashboard.materials"
                  :key="item.id"
                  :value="item.name"
                >
                  {{ item.name }}
                </option>
              </select></label
            >
            <label
              >单件重量(g)<input
                v-model.number="productForm.weight_g"
                min="0"
                step="0.01"
                type="number"
            /></label>
            <label
              >单件时间(h)<input
                v-model.number="productForm.duration_hours"
                min="0"
                step="0.01"
                type="number"
            /></label>
            <label
              >默认数量<input
                v-model.number="productForm.default_quantity"
                min="1"
                type="number"
            /></label>
            <QuoteEditor
              v-model="productForm.quoted_price"
              :existing="!!productForm.id"
              :settings="dashboard?.settings"
              :materials="dashboard?.materials || []"
              :input="{
                material: productForm.material_name,
                weight: productForm.weight_g,
                hours: productForm.duration_hours,
                quantity: productForm.default_quantity,
                designFee: 0,
              }"
            />
            <div
              v-if="canUploadImage"
              class="product-image-editor md:col-span-2"
              tabindex="0"
              role="group"
              aria-label="产品图片粘贴区"
            >
              <strong>产品图片</strong>
              <p>复制截图或图片，在此按 Ctrl+V 粘贴，也可以选择本地图片。</p>
              <img
                v-if="imagePreview || existingImage"
                :src="imagePreview || existingImage"
                alt="产品图片预览"
                class="product-image-preview"
              />
              <p v-if="pendingProductImage" role="status">
                图片已选择，保存产品后上传。
              </p>
              <p v-else-if="existingImage">当前产品图片；粘贴新图片可替换。</p>
              <label
                >选择本地图片<input
                  :key="imageInputKey"
                  accept="image/jpeg,image/png,image/webp"
                  type="file"
                  :disabled="saving"
                  @change="selectImage"
              /></label>
              <small>JPEG / PNG / WebP，最大 5MB；每个产品一张图片。</small>
              <p v-if="imageError" role="alert" class="image-error">
                {{ imageError }}
              </p>
              <button
                v-if="pendingProductImage"
                type="button"
                class="action-button secondary"
                :disabled="saving"
                @click="clearImage"
              >
                取消本次图片
              </button>
            </div>
          </div>
          <button class="action-button mt-4" type="submit" :disabled="saving">
            <Save class="size-4" />{{
              saving ? "正在保存产品和图片…" : "保存产品"
            }}
          </button>
        </form>
      </LegacyDialog>
      <div class="panel-card">
        <div class="legacy-panel-head">
          <h2>产品库</h2>
          <span>{{ listPages.products!.total }} 个产品</span>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>名称</th>
                <th>图片</th>
                <th>客户</th>
                <th>默认材料</th>
                <th>默认料重(g)</th>
                <th>默认耗时(h)</th>
                <th>数量</th>
                <th>默认报价</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="product in dashboard.products" :key="product.id">
                <td>{{ product.legacy_id || "新增" }}</td>
                <td>{{ product.name }}</td>
                <td>
                  <a
                    v-if="product.image_url && !brokenImages.has(product.id)"
                    :href="product.image_url"
                    target="_blank"
                    rel="noopener"
                    ><img
                      :src="product.image_url"
                      :alt="product.name"
                      @error="brokenImages.add(product.id)"
                      loading="lazy"
                      class="record-image"
                  /></a>
                </td>
                <td>{{ product.customer || "—" }}</td>
                <td>{{ product.material_name || "—" }}</td>
                <td>{{ product.weight_g || "—" }}</td>
                <td>{{ product.duration_hours || "—" }}</td>
                <td>{{ product.default_quantity }}</td>
                <td>{{ money(product.quoted_price) }}</td>
                <td>
                  <div class="row-actions">
                    <button @click="showProductRecords(product.name)">
                      打印记录
                    </button>
                    <button
                      v-if="canOperate"
                      @click="
                        showForm = true;
                        editProduct(product);
                      "
                    >
                      编辑</button
                    ><button
                      v-if="canOperate"
                      class="danger"
                      @click="archiveProduct(product)"
                    >
                      删除
                    </button>
                  </div>
                </td>
              </tr>
              <tr v-if="!dashboard.products.length">
                <td colspan="10">暂无产品，点击“+ 添加产品”</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>
  </template>
</template>
<style scoped>
.product-image-editor {
  display: grid;
  gap: 10px;
  padding: 16px;
  border: 1px dashed var(--border);
  border-radius: 12px;
  background: var(--muted);
}
.product-image-editor:focus {
  outline: 2px solid var(--ring);
  outline-offset: 2px;
}
.product-image-editor p,
.product-image-editor small {
  margin: 0;
  color: var(--muted-foreground);
}
.product-image-preview {
  width: 100%;
  max-width: 320px;
  height: 180px;
  object-fit: contain;
  border-radius: 8px;
  background: var(--card);
}
.product-image-editor .image-error {
  color: var(--destructive);
}
.product-image-editor button {
  justify-self: start;
}
</style>
