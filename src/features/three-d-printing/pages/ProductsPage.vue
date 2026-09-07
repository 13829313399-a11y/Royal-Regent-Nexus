<script setup lang="ts">
import { reactive } from "vue";
const brokenImages = reactive(new Set<string>());
import PageControls from "../components/PageControls.vue";
import { useWorkspaceContext } from "../context";
const {
  listPages,
  loadPage,
  dashboard,
  loading,
  saving,
  productSearch,
  canOperate,
  canUploadImage,
  productForm,
  imageInputKey,
  visibleProducts,
  money,
  resetProductForm,
  editProduct,
  selectProductImage,
  submitProduct,
  archiveProduct,
  ImagePlus,
  Save,
} = useWorkspaceContext();
</script>
<template>
  <template v-if="dashboard">
    <section class="space-y-5">
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
      <form
        v-if="canOperate"
        class="panel-card p-5"
        @submit.prevent="submitProduct"
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
            >产品名称<input v-model="productForm.name" required maxlength="255"
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
      <div class="panel-card p-5">
        <div class="section-heading">
          <div>
            <h2>产品库</h2>
            <p>
              {{ dashboard.products.length }}
              个有效产品，历史图片已迁移为独立文件。
            </p>
          </div>
          <input
            v-model="productSearch"
            class="compact-input"
            placeholder="搜索产品、客户或材料"
          />
        </div>
        <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          <article
            v-for="product in visibleProducts"
            :key="product.id"
            class="overflow-hidden rounded-xl border border-slate-200 bg-white"
          >
            <div class="aspect-[4/3] bg-slate-100">
              <img
                v-if="product.image_url && !brokenImages.has(product.id)"
                :src="product.image_url"
                :alt="product.name"
                @error="brokenImages.add(product.id)"
                class="size-full object-cover"
                loading="lazy"
              />
              <div
                v-else
                class="flex size-full items-center justify-center text-slate-400"
              >
                <ImagePlus class="size-8" />
              </div>
            </div>
            <div class="p-4">
              <h3 class="truncate font-semibold text-slate-950">
                {{ product.name }}
              </h3>
              <small class="text-slate-400">{{
                product.legacy_id || product.id
              }}</small>
              <p class="mt-1 truncate text-xs text-slate-500">
                {{ product.customer || "未登记客户" }} ·
                {{ product.material_name || "未登记材料" }}
              </p>
              <div class="mt-3 flex justify-between text-xs text-slate-600">
                <span
                  >{{ product.weight_g }}g / {{ product.duration_hours }}h</span
                ><strong>{{ money(product.quoted_price) }}</strong>
              </div>
              <div v-if="canOperate" class="row-actions mt-4">
                <button type="button" @click="editProduct(product)">编辑</button
                ><button
                  class="danger"
                  type="button"
                  @click="archiveProduct(product)"
                >
                  停用
                </button>
              </div>
            </div>
          </article>
        </div>
      </div>
    </section>
  </template>
</template>
