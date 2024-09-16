import torch
import torch.nn as nn

from transformers import CLIPVisionModel, CLIPImageProcessor, CLIPVisionConfig, AutoProcessor, AutoModelForCausalLM 


class CLIPVisionTower(nn.Module):
    def __init__(self, vision_tower, args, delay_load=False):
        super().__init__()

        self.is_loaded = False

        self.vision_tower_name = vision_tower
        self.select_layer = args.mm_vision_select_layer
        self.select_feature = getattr(args, 'mm_vision_select_feature', 'patch')

        if not delay_load:
            self.load_model()
        elif getattr(args, 'unfreeze_mm_vision_tower', False):
            self.load_model()
        else:
            self.cfg_only = CLIPVisionConfig.from_pretrained(self.vision_tower_name)

    def load_model(self, device_map=None):
        if self.is_loaded:
            print('{} is already loaded, `load_model` called again, skipping.'.format(self.vision_tower_name))
            return

        self.image_processor = CLIPImageProcessor.from_pretrained(self.vision_tower_name)
        self.vision_tower = CLIPVisionModel.from_pretrained(self.vision_tower_name, device_map=device_map)
        self.vision_tower.requires_grad_(False)

        self.is_loaded = True

    def feature_select(self, image_forward_outs):
        image_features = image_forward_outs.hidden_states[self.select_layer]
        if self.select_feature == 'patch':
            image_features = image_features[:, 1:]
        elif self.select_feature == 'cls_patch':
            image_features = image_features
        else:
            raise ValueError(f'Unexpected select feature: {self.select_feature}')
        return image_features

    @torch.no_grad()
    def forward(self, images):
        if type(images) is list:
            image_features = []
            for image in images:
                image_forward_out = self.vision_tower(image.to(device=self.device, dtype=self.dtype).unsqueeze(0), output_hidden_states=True)
                image_feature = self.feature_select(image_forward_out).to(image.dtype)
                image_features.append(image_feature)
        else:
            image_forward_outs = self.vision_tower(images.to(device=self.device, dtype=self.dtype), output_hidden_states=True)
            image_features = self.feature_select(image_forward_outs).to(images.dtype)
        return image_features, image_features

    @property
    def dummy_feature(self):
        return torch.zeros(1, self.hidden_size, device=self.device, dtype=self.dtype)

    @property
    def dtype(self):
        return self.vision_tower.dtype

    @property
    def device(self):
        return self.vision_tower.device

    @property
    def config(self):
        if self.is_loaded:
            return self.vision_tower.config
        else:
            return self.cfg_only

    @property
    def hidden_size(self):
        return self.config.hidden_size

    @property
    def num_patches_per_side(self):
        return self.config.image_size // self.config.patch_size

    @property
    def num_patches(self):
        return (self.config.image_size // self.config.patch_size) ** 2





class FlorenceVisionTower(nn.Module):
    def __init__(self, vision_tower, args, delay_load=False):
        super().__init__()

        self.is_loaded = False
        self.vision_tower_name = vision_tower

        if not delay_load:
            self.load_model()
        elif getattr(args, 'unfreeze_mm_vision_tower', False):
            self.load_model()
        else:
            self.load_model()


    def load_model(self, device_map=None):
        if self.is_loaded:
            print('{} is already loaded, `load_model` called again, skipping.'.format(self.vision_tower_name))
            return

        self.image_processor = AutoProcessor.from_pretrained(self.vision_tower_name, trust_remote_code=True)
        self.vision_tower = AutoModelForCausalLM.from_pretrained(self.vision_tower_name, trust_remote_code=True).to(torch.bfloat16)
        self.vision_tower.requires_grad_(False)

        self.is_loaded = True


    @torch.no_grad()
    def forward(self, images):
        
        ## hard code for the task prompt 
        # task = [
        #     'Describe in detail what is shown in the image.',
        #     'What is the text in the image?',
        #     'Locate the objects in the image, with their descriptions.',
        #     'Locate the region proposals in the image.'
        # ]

        task_ids = torch.tensor([
            [0, 47066, 21700, 11, 4617, 99, 16, 2343, 11, 5, 2274, 4, 2, 1],
            [0, 2264, 16, 5, 2788, 11, 5, 2274, 116, 2, 1, 1, 1, 1],
            [0, 574, 22486, 5, 8720, 11, 5, 2274, 6, 19, 49, 24173, 4, 2]
        ]).to(device=self.device)

        # task = [
        #     'What is the text in the image?',
        #     'What is the text in the image, with regions?',
        #     'What does the image describe?',
        #     'Describe in detail what is shown in the image.',
        #     'Describe with a paragraph what is shown in the image.',
        #     'Locate the objects with category name in the image.',
        #     'Locate the objects in the image, with their descriptions.',
        #     'Locate the region proposals in the image.'
        # ]


        # task_ids = torch.tensor([
        #     [0, 2264, 16, 5, 2788, 11, 5, 2274, 116, 2, 1, 1, 1, 1],
        #     [0, 2264, 16, 5, 2788, 11, 5, 2274, 6, 19, 3806, 116, 2, 1],
        #     [0, 2264, 473, 5, 2274, 6190, 116, 2, 1, 1, 1, 1, 1, 1],
        #     [0, 47066, 21700, 11, 4617, 99, 16, 2343, 11, 5, 2274, 4, 2, 1],
        #     [0, 47066, 21700, 19, 10, 17818, 99, 16, 2343, 11, 5, 2274, 4, 2],
        #     [0, 574, 22486, 5, 8720, 19, 4120, 766, 11, 5, 2274, 4, 2, 1],
        #     [0, 574, 22486, 5, 8720, 11, 5, 2274, 6, 19, 49, 24173, 4, 2],
        #     [0, 574, 22486, 5, 976, 5327, 11, 5, 2274, 4, 2, 1, 1, 1]
        # ]).to(device=self.device)


        with torch.no_grad():
            generated_ids, image_feature, encoder_last_hidden_state = self.vision_tower.generate(
                input_ids=task_ids,
                pixel_values=images,
                max_new_tokens=1,
                do_sample=False,
                num_beams=1,
            )
            return image_feature, encoder_last_hidden_state


    @property
    def dummy_feature(self):
        return torch.zeros(1, self.hidden_size, device=self.device, dtype=self.dtype)

    @property
    def dtype(self):
        return self.vision_tower.dtype

    @property
    def device(self):
        return self.vision_tower.device

    @property
    def config(self):
        if self.is_loaded:
            return self.vision_tower.config
        else:
            return self.cfg_only

    @property
    def hidden_size(self):
        return self.config.hidden_size

    @property
    def num_patches_per_side(self):
        return self.config.image_size // self.config.patch_size

    @property
    def num_patches(self):
        return (self.config.image_size // self.config.patch_size) ** 2
