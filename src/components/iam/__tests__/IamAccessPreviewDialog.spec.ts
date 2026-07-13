import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import IamAccessPreviewDialog from '@/components/iam/IamAccessPreviewDialog.vue'

describe('IamAccessPreviewDialog', () => {
  it('shows the Chinese permission label above the original permission code', () => {
    const wrapper = mount(IamAccessPreviewDialog, {
      props: {
        reason: '核对中文权限名称',
        permissions: [{
          code: 'carton_mark:photo_upload',
          name: 'carton_mark:photo_upload',
          module_code: 'carton_mark',
          module_name: '箱唛管理',
          action: 'photo_upload',
          risk_level: 'normal',
          scope_type: 'department',
          status: 'active',
          sort_order: 1,
          applicable_departments: ['qa'],
          requires_global_factory: false,
          scope_guidance: '仅 QA 部门可配置。',
        }],
        preview: {
          preview_token: 'preview-token',
          base_revision: 1,
          diffs: [{
            permission_code: 'carton_mark:photo_upload',
            factory_id: 'huakang-a',
            department: 'qa',
            before: 'none',
            after: 'allow',
            risk_level: 'normal',
          }],
          requires_approval: false,
          high_risk: false,
        },
      },
    })

    expect(wrapper.get('strong').text()).toBe('上传箱唛实拍')
    expect(wrapper.get('code').text()).toContain('carton_mark:photo_upload')
    expect(wrapper.text().match(/carton_mark:photo_upload/g)).toHaveLength(1)
  })
})
