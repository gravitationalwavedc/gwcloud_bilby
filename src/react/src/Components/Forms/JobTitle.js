import React from "react";
import { HiOutlinePencil, HiOutlineCheck, HiOutlineX} from "react-icons/hi";
import EdiText from "react-editext";

const EditButton = () => <React.Fragment><HiOutlinePencil /> edit</React.Fragment>
const SaveButton = () => <HiOutlineCheck/>
const CancelButton = () => <HiOutlineX/>

const JobTitle = ({title, setTitle, description, setDescription}) => {
  return (
    <React.Fragment>
          <EdiText 
            type="text" 
            value={title}
            viewProps={{className: "h1"}}
            onSave={(value) => setTitle(value)}
            hint="You can use letters, numbers, underscores and hyphens."
            editButtonContent={<EditButton/>}
            editButtonClassName="edit-button"
            saveButtonContent={<SaveButton />}
            saveButtonClassName="save-button"
            cancelButtonContent={<CancelButton />}
            cancelButtonClassName="cancel-button"
            hideIcons
          />
          <EdiText 
            type="text" 
            value={description}
            onSave={(value) => setDescription(value)}
            editButtonContent={<EditButton/>}
            editButtonClassName="edit-button"
            saveButtonContent={<SaveButton />}
            saveButtonClassName="save-button"
            cancelButtonContent={<CancelButton />}
            cancelButtonClassName="cancel-button"
            hideIcons
          />
    </React.Fragment>
  );
}

export default JobTitle;
