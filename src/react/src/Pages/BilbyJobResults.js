import React from "react";
import { graphql, createPaginationContainer } from "react-relay";
import _ from "lodash";
import BilbyBasePage from "./BilbyBasePage";
import JobResults from "../Components/Results/JobResults";

class BilbyJobResults extends React.Component {
    constructor(props) {
        super(props);
        this.routing = {
            match: this.props.match,
            router: this.props.router,
            breadcrumbPaths: [
                {name: 'Job Results', path: '/bilby/job-results/'}
            ]
        }
    }


    render() {
        return (
            <BilbyBasePage title='Bilby Job Results' {...this.routing}>
                <JobResults jobId={this.props.jobId} {...this.props}/>
            </BilbyBasePage>
        )
    }
}

export default BilbyJobResults;
// export default createPaginationContainer(BilbyJobList,
//     {
//         data: graphql`
//             fragment BilbyJobList_data on Query {
//                 bilbyJobs(
//                     first: $count,
//                     after: $cursor,
//                     orderBy: $orderBy
//                 ) @connection(key: "BilbyJobList_bilbyJobs") {
//                     edges {
//                         node {
//                             id
//                             name
//                             description
//                             lastUpdated
//                             jobStatus
//                         }
//                     }
//                   }
//             }
//         `,
//     },
//     {
//         direction: 'forward',
//         query: graphql`
//             query BilbyJobListForwardQuery(
//                 $count: Int!,
//                 $cursor: String,
//                 $orderBy: String
//             ) {
//               ...BilbyJobList_data
//             }
//         `,
//         getConnectionFromProps(props) {
//             return props.data && props.data.bilbyJobs
//         },

//         getFragmentVariables(previousVariables, totalCount) {
//             return {
//                 ...previousVariables,
//                 count: totalCount
//             }
//         },

//         getVariables(props, {count, cursor}, {orderBy}) {
//             return {
//                 count,
//                 cursor,
//                 orderBy,
//             }
//         }
//     }
// )