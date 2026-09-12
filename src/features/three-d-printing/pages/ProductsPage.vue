<script setup lang="ts">
import { ref, watch } from "vue";
import LegacyDialog from "../components/LegacyDialog.vue";
import { reactive } from "vue";
const brokenImages = reactive(new Set<string>());
import PageControls from "../components/PageControls.vue";
import { useWorkspaceContext } from "../context";
const {
  listPages,
  loadPage,
  dashboard,
  saving,
  errorMessage,
  canOperate,
  canUploadImage,
  productForm,
  imageInputKey,
  money,
  resetProductForm,
  editProduct,
  selectProductImage,
  submitProduct,
  archiveProduct,
  Save,
} = useWorkspaceContext();
const showForm = ref(false);
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
      <LegacyDialog v-if="showForm" title="产品" @close="showForm = false">
        <form
          v-if="canOperate"
          class="panel-card p-5"
          @submit.prevent="saveForm"
        >
          <div class="section-heading">
            <div>
              <h2>{{ productForm.id ? "编辑产品" : "新增产品" }}</h2>
              <p>
                产品资料先保存到数据库；选中的图片上传成功后才会结束本次保存。
              </p>
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
            <label
              >报价<input
                v-model.number="productForm.quoted_price"
                min="0"
                step="0.01"
                type="number"
            /></label>
            <label v-if="canUploadImage"
              >产品图片<input
                :key="imageInputKey"
                accept="image/jpeg,image/png,image/webp"
                type="file"
                @change="selectProductImage"
              /><small
                >JPEG / PNG / WebP，最大 5MB；云端会压缩为安全尺寸。</small
              ></label
            >
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
                <th v-if="canOperate">操作</th>
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
                <td v-if="canOperate">
                  <div class="row-actions">
                    <button
                      @click="
                        showForm = true;
                        editProduct(product);
                      "
                    >
                      编辑</button
                    ><button class="danger" @click="archiveProduct(product)">
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
